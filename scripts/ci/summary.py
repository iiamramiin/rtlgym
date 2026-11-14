"""Planning and reporting for scripts/ci/eval.sh.

  python summary.py plan MODELS TASKS SAMPLES TURNS PAIRED ARMS
      the most API calls the run can make
  python summary.py report DIR
      Markdown summary of the result files in DIR: inconclusive and error counts,
      tokens per model, and paired outcomes (the main table comes from
      `rtlgym report`)
"""

import json
import sys
from pathlib import Path


def plan(models: int, tasks: int, samples: int, turns: int, paired: bool, arms: int) -> int:
    """Upper bound on API calls. Paired: one shared first attempt, then up to
    turns - 1 more in each of the two arms. Unpaired: every arm runs every turn."""
    per_episode = 1 + 2 * (turns - 1) if paired else arms * turns
    return models * tasks * samples * per_episode


def _load(folder: Path):
    arms, pairs = [], []
    for p in sorted(folder.glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except ValueError:
            continue
        if "summary" in d:
            arms.append(d["summary"])
        elif "paired" in d:
            pairs.append((d["meta"].get("model") or d["meta"].get("agent"), d["paired"]))
    return arms, pairs


def _name(s: dict) -> str:
    return s.get("model") or s.get("agent") or "?"


def report(folder: str) -> str:
    arms, pairs = _load(Path(folder))
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
        out.append("\nInformative: first attempt not accepted (only these can differ between "
                   "the arms). Discordant: solved in exactly one arm.")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    if sys.argv[1] == "plan":
        m, t, s, n = (int(x) for x in sys.argv[2:6])
        print(plan(m, t, s, n, sys.argv[6] == "true", int(sys.argv[7])))
    else:
        print(report(sys.argv[2]), end="")
