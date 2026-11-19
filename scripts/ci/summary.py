"""Planning and reporting for scripts/ci/eval.sh.

  python summary.py plan MODELS TASKS SAMPLES TURNS PAIRED ARMS
      the most API calls the run can make
  python summary.py report DIR
      Markdown summary of the result files in DIR: inconclusive and error counts,
      tokens per model, acceptance by task kind, repair sizes, and paired outcomes
      (the main table comes from `rtlgym report`)
"""

import json
import sys
from collections import Counter
from pathlib import Path
from statistics import median


def plan(models: int, tasks: int, samples: int, turns: int, paired: bool, arms: int) -> int:
    """Upper bound on API calls. Paired: one shared first attempt, then up to
    turns - 1 more in each of the two arms. Unpaired: every arm runs every turn."""
    per_episode = 1 + 2 * (turns - 1) if paired else arms * turns
    return models * tasks * samples * per_episode


def _load(folder: Path):
    # Also support direct script invocation, where scripts/ci is on sys.path.
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)
    from rtlgym.cli import refresh_report

    arms, pairs = [], []
    for p in sorted(folder.glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except ValueError:
            continue
        if "summary" in d:
            if d.get("episodes"):
                d = refresh_report(d)
            arms.append((d["summary"], d.get("episodes", [])))
        elif "paired" in d:
            pairs.append((d["meta"].get("model") or d["meta"].get("agent"), d["paired"]))
    return arms, pairs


def _name(s: dict) -> str:
    return s.get("model") or s.get("agent") or "?"


def _by_task_kind(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row.get("task_kind", "design"), []).append(row)
    return groups


def _edit_median(value: float | None, count: int) -> str:
    return f"{value:g} (n={count})" if value is not None else "— (n=0)"


def _arm_kind_counts(rows: list[dict]) -> dict:
    """Recover kind-level counts from episodes when only raw rows are available."""
    counts = {}
    for kind, group in _by_task_kind(rows).items():
        n = len(group)
        first = sum(bool(episode.get("pass@1")) for episode in group)
        solved = sum(bool(episode.get("solved")) for episode in group)
        record = counts[kind] = {
            "episodes": n,
            "errors": sum(bool(episode.get("error")) for episode in group),
            "pass@1_count": f"{first}/{n}",
            "solved_count": f"{solved}/{n}",
            "truncated_attempts": sum(episode.get("truncated_attempts", 0) for episode in group),
        }
        if kind == "repair":
            all_edits, accepted_edits = [], []
            for episode in group:
                for attempt in episode.get("trajectory", []):
                    size = attempt.get("lines_changed")
                    if type(size) is int and size >= 0:
                        all_edits.append(size)
                        if attempt.get("solved"):
                            accepted_edits.append(size)
            record["lines_changed"] = {
                "attempts": len(all_edits),
                "median": median(all_edits) if all_edits else None,
                "accepted_attempts": len(accepted_edits),
                "accepted_median": median(accepted_edits) if accepted_edits else None,
            }
    return counts


def _report_arms_by_kind(out: list[str], arm_files: list[tuple[dict, list[dict]]]) -> None:
    if not any(arm.get("by_kind") or any("task_kind" in row for row in rows) for arm, rows in arm_files):
        return
    out.append("\n### Acceptance by task kind\n")
    out.append("| Model | Feedback | Kind | Episodes (errors) | First attempt | Within turn budget | "
               "Truncated attempts |")
    out.append("|---|---|---|---:|---:|---:|---:|")
    repair_rows = []
    for arm, rows in arm_files:
        name, feedback = _name(arm), arm["feedback"]
        counts = arm.get("by_kind") or _arm_kind_counts(rows)
        for kind, group in sorted(counts.items()):
            out.append(f"| {name} | {feedback} | {kind} | {group['episodes']} ({group['errors']}) | "
                       f"{group['pass@1_count']} | {group['solved_count']} | "
                       f"{group.get('truncated_attempts', 0)} |")
            if kind == "repair":
                edits = group.get("lines_changed") or {}
                all_edits = _edit_median(edits.get("median"), edits.get("attempts", 0))
                accepted = _edit_median(edits.get("accepted_median"), edits.get("accepted_attempts", 0))
                repair_rows.append(f"| {name} | {feedback} | {all_edits} | {accepted} |")
    if repair_rows:
        out.append("\n### Repair edit size\n")
        out.append("| Model | Feedback | All graded attempts | Accepted attempts |")
        out.append("|---|---|---:|---:|")
        out.extend(repair_rows)
        out.append("\nCells show median lines changed from the starter (n = attempts with an edit "
                   "count). Zero is included. Each feedback arm counts its shared first submission "
                   "once. Accepted attempts satisfied the grading checks.")


def _report_pairs_by_kind(out: list[str], pairs: list[tuple[str, dict]]) -> None:
    if not any(pair.get("by_kind") or any("task_kind" in row for row in pair.get("rows", []))
               for _, pair in pairs):
        return
    out.append("\n### Paired outcomes by task kind\n")
    out.append("| Model | Kind | Episodes | Solved in both | Only full | Only none | In neither | Errored |")
    out.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for model, pair in pairs:
        counts = pair.get("by_kind") or {
            kind: {"episodes": len(rows), "outcomes": Counter(row["outcome"] for row in rows)}
            for kind, rows in _by_task_kind(pair.get("rows", [])).items()
        }
        for kind, group in sorted(counts.items()):
            count = group["outcomes"]
            out.append(f"| {model} | {kind} | {group['episodes']} | {count.get('both', 0)} | "
                       f"{count.get('only_full', 0)} | {count.get('only_none', 0)} | "
                       f"{count.get('neither', 0)} | {count.get('errored', 0)} |")


def _report_verify(out: list[str], arms: list[dict]) -> None:
    if not any("verify" in arm.get("by_kind", {}) for arm in arms):
        return
    out.append("\n### Verification checker results\n")
    out.append("| Model | Feedback | Episodes (graded) | False alarms | Invalid | Inconclusive | Truncated | "
               "Mutants caught | Mean family coverage | Mean reward |")
    out.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for arm in arms:
        group = arm.get("by_kind", {}).get("verify")
        if group is None:
            continue
        counts = group["verification"]
        coverage = counts["mean_weighted_caught"]
        coverage = f"{coverage:.1%}" if coverage is not None else "n/a"
        out.append(f"| {_name(arm)} | {arm['feedback']} | {counts['episodes']} "
                   f"({counts['graded_episodes']}) | {counts['false_alarm_episodes']} | "
                   f"{counts['invalid_episodes']} | {counts['inconclusive_episodes']} | "
                   f"{counts.get('truncated_episodes', 0)} | "
                   f"{counts['caught']}/{counts['mutants_total']} | {coverage} | {counts['mean_score']} |")
    out.append("\nEach episode contributes its final checker. Mutant counts are checks across "
               "episodes. Family coverage weights mutation families equally. False alarms, "
               "invalid checkers, truncated replies, inconclusive grades and episodes with errors "
               "earn zero reward.")
    out.append("\n| Model | Feedback | Mean assertions | Mean state bits | Mean source bytes |")
    out.append("|---|---|---:|---:|---:|")
    for arm in arms:
        group = arm.get("by_kind", {}).get("verify")
        if group is not None:
            counts = group["verification"]
            out.append(f"| {_name(arm)} | {arm['feedback']} | {counts.get('mean_assertions', 'n/a')} | "
                       f"{counts.get('mean_state_bits', 'n/a')} | "
                       f"{counts.get('mean_checker_bytes', 'n/a')} |")


def report(folder: str) -> str:
    arm_files, pairs = _load(Path(folder))
    arms = [summary for summary, _ in arm_files]
    out = []
    inconclusive = sum(s.get("inconclusive_attempts", 0) for s in arms)
    errors = sum(s.get("errors", 0) for s in arms)
    flag = "**WARNING:** " if inconclusive else ""
    out.append(f"{flag}**Inconclusive attempts: {inconclusive}** (the grader could not "
               "decide, e.g. a tool hit its time limit; these count as not accepted)."
               + (" Check the per-arm rows below." if inconclusive else ""))
    out.append(f"\n**Errored episodes: {errors}** (e.g. API errors; counted as unsolved).")
    details = [s for s in arms if s.get("inconclusive_attempts") or s.get("errors")]
    if details:
        out.append("")
    for s in details:
        if True:
            out.append(f"- {_name(s)}, feedback {s['feedback']}: "
                       f"{s.get('inconclusive_attempts', 0)} inconclusive, "
                       f"{s.get('errors', 0)} errored")

    truncated = sum(s.get("truncated_attempts", 0) for s in arms)
    out.append(f"\n**Truncated attempts: {truncated}** (the output limit was reached without "
               "complete extracted code; these earn zero reward).")

    failure_keys = ("frontend_failure_attempts", "resource_failure_attempts", "truncated_attempts")
    if any(key in s for s in arms for key in failure_keys):
        out.append("\n### Front-end, resource and truncated attempts by arm\n")
        out.append("| Model | Feedback | Front-end failures | Resource failures | Truncated |")
        out.append("|---|---|---:|---:|---:|")
        for s in arms:
            front_end, resource, cut_off = (s.get(key, "n/a") for key in failure_keys)
            out.append(f"| {_name(s)} | {s['feedback']} | {front_end} | {resource} | {cut_off} |")

    fallback_key = "sim_frontend_fallback_attempts"
    if any(fallback_key in s for s in arms):
        out.append("\n### Icarus simulation front-end retries\n")
        out.append("| Model | Feedback | Compiled after sv2v |")
        out.append("|---|---|---:|")
        for s in arms:
            out.append(f"| {_name(s)} | {s['feedback']} | {s.get(fallback_key, 'n/a')} |")

    _report_arms_by_kind(out, arm_files)
    _report_verify(out, arms)

    # Tokens per model: every arm's own calls, plus the shared first calls of pairs.
    totals: dict[str, dict] = {}
    for s in arms:
        t = totals.setdefault(_name(s), {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        for k in t:
            t[k] += (s.get("usage") or {}).get(k, 0)
    for model, p in pairs:
        t = totals.setdefault(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        for k in t:
            t[k] += (p.get("shared_first") or {}).get(k, 0)
    out.append("\n### Tokens per model\n")
    out.append("| Model | API calls | Input tokens | Output tokens (thinking included) |")
    out.append("|---|---:|---:|---:|")
    for model, t in totals.items():
        out.append(f"| {model} | {t['calls']:,} | {t['input_tokens']:,} | "
                   f"{t['output_tokens']:,} |")
    out.append("\nCost = input tokens x input price + output tokens x output price; check "
               "the current prices at https://platform.claude.com/docs/en/about-claude/pricing.")

    if pairs:
        out.append("\n### Paired outcomes (same first attempt in both arms)\n")
        out.append("| Model | Episodes | Solved in both | Only full | Only none | In neither "
                   "| Errored | Informative | Discordant | Exact McNemar p |")
        out.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for model, p in pairs:
            o = p["outcomes"]
            out.append(f"| {model} | {p['episodes']} | {o['both']} | {o['only_full']} | "
                       f"{o['only_none']} | {o['neither']} | {o.get('errored', 0)} | "
                       f"{p.get('informative_episodes', 'n/a')} | {p['discordant_pairs']} | "
                       f"{p.get('mcnemar_exact_p', 'n/a')} |")
        if any(p.get("by_verification") for _, p in pairs):
            out.append("\n### Paired outcomes by verification mode\n")
            out.append("| Model | Verification | Episodes | Solved in both | Only full | Only none "
                       "| In neither | Errored | Informative | Discordant | Exact McNemar p |")
            out.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
            labels = {"formal": "Formal enabled", "simulation_only": "Simulation only"}
            for model, p in pairs:
                for mode, group in sorted(p.get("by_verification", {}).items()):
                    o = group["outcomes"]
                    out.append(f"| {model} | {labels[mode]} | {group['episodes']} | {o['both']} | "
                               f"{o['only_full']} | {o['only_none']} | {o['neither']} | {o['errored']} | "
                               f"{group['informative_episodes']} | {group['discordant_pairs']} | "
                               f"{group['mcnemar_exact_p']} |")
        _report_pairs_by_kind(out, pairs)
        out.append("\nInformative: first attempt not accepted (only these can differ between "
                   "the arms). Discordant: solved in exactly one arm.")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    if sys.argv[1] == "plan":
        m, t, s, n = (int(x) for x in sys.argv[2:6])
        print(plan(m, t, s, n, sys.argv[6] == "true", int(sys.argv[7])))
    else:
        print(report(sys.argv[2]), end="")
