# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Command-line entry point: python -m rtlgym <command>."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .agents import make_agent
from .agents.claude import DEFAULT_MODEL
from .checks import _FENCE_RE, _MODULE_RE, _OPEN_FENCE_RE
from .env import RTLEnv, format_feedback, is_solved
from .evaluator import EvalResult, evaluate
from .stats import clopper_pearson, format_ci
from .task import DEFAULT_TASKS_ROOT, list_tasks, load_task
from .tools import tool_versions

REPO_ROOT = Path(__file__).resolve().parent.parent
_TASKS_HELP = "all, design, repair, verify, or comma-separated task IDs"


def _tasks_arg(value: str, root: Path) -> list[str]:
    all_ids = list_tasks(root)
    if value == "all":
        return all_ids
    if value in ("design", "repair", "verify"):
        ids = [tid for tid in all_ids if load_task(tid, root).kind == value]
    else:
        ids = [t.strip() for t in value.split(",") if t.strip()]
    unknown = set(ids) - set(all_ids)
    if unknown:
        sys.exit(f"unknown task(s): {', '.join(sorted(unknown))}")
    if not ids:
        sys.exit("no tasks selected")
    return ids


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


def _git_commit(cwd: Path = REPO_ROOT) -> str:
    """The commit the code came from, with "-dirty" if tracked files were changed
    since (results from uncommitted code must not claim a clean commit)."""
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]

    def git(*argv: str) -> str:
        return subprocess.run(["git", "-c", "core.fileMode=false", *argv], cwd=cwd,
                              capture_output=True, text=True, timeout=10).stdout.strip()
    try:
        head = git("rev-parse", "HEAD")
        if not head:
            return "unknown"
        return head + ("-dirty" if git("status", "--porcelain", "--untracked-files=no") else "")
    except Exception:  # noqa: BLE001
        return "unknown"


def cmd_list(args) -> int:
    for tid in _tasks_arg(args.tasks, args.tasks_root):
        t = load_task(tid, args.tasks_root)
        fv = f"formal depth {t.formal.get('depth')}" if t.has_formal else "no formal"
        relation = f" ({t.kind} of {t.parent_id})" if t.kind in ("repair", "verify") else ""
        print(f"{tid:20s} {t.difficulty:8s} {fv:16s} {', '.join(t.tags)}{relation}")
    return 0


def cmd_score(args) -> int:
    task = load_task(args.task, args.tasks_root)
    if task.kind == "verify" and args.no_formal:
        sys.exit("verification tasks require their formal checker run")
    code = Path(args.file).read_text()
    res = evaluate(task, code, use_cache=not args.no_cache, use_formal=not args.no_formal)
    print(format_feedback(res, "full"))
    print(json.dumps({"score": res.score, "breakdown": res.breakdown,
                      "formal": res.formal_status, "timings_s": res.timings_s,
                      **({"verification": res.verification}
                         if getattr(res, "verification", None) else {})}, indent=2))
    return 0


def cmd_baselines(args) -> int:
    """Score the reference and every hand-written candidate: a sanity check that
    the reward ranks known-good above known-bad and blocks known hacks."""
    rows = []
    jobs = []
    for tid in _tasks_arg(args.tasks, args.tasks_root):
        task = load_task(tid, args.tasks_root)
        if task.kind == "verify" and args.no_formal:
            sys.exit("verification tasks require their formal checker run")
        for path in [task.ref_path, *task.candidates()]:
            jobs.append((task, path))
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda j: evaluate(j[0], j[1].read_text(),
                                                   use_cache=not args.no_cache,
                                                   use_formal=not args.no_formal), jobs))
    versions = tool_versions()
    for (task, path), r in zip(jobs, results, strict=True):
        name = "ref.sv" if path == task.ref_path else path.name
        rows.append({"task": task.id, "candidate": name, "score": r.score,
                     "tests": f"{r.tests_passed}/{r.tests_total}", "formal": r.formal_status,
                     "formal_message": r.formal_message, "frontend_errors": r.frontend_errors,
                     "resource_failures": r.resource_failures, "ppa_unavailable": r.ppa_unavailable,
                     "sim_frontend": r.sim_frontend, "synth_frontend": r.synth_frontend,
                     "formal_frontend": r.formal_frontend,
                     "timings_s": r.timings_s, "tools": versions,
                     "compile": r.compile_ok, "lint_warn": len(r.lint_warnings),
                     "cells": r.cells, "ref_cells": r.ref_cells, "depth": r.depth,
                     "violations": r.violations, "breakdown": r.breakdown,
                     "task_kind": task.kind, "accepted": r.accepted,
                     "is_starter": path == task.start_path,
                     **({"verification": r.verification} if getattr(r, "verification", None) else {})})
    print(f"{'task':18s} {'candidate':30s} {'score':>6s} {'tests':>6s} {'formal':>8s} "
          f"{'cells':>6s} {'ref':>5s} {'warn':>4s}  note")
    for row in rows:
        note = "; ".join(row["violations"])[:50] or ("" if row["compile"] else "compile error")
        if row["frontend_errors"]:
            note = "front end could not parse: " + ", ".join(row["frontend_errors"])
        elif row["resource_failures"]:
            note = "resource limit: " + ", ".join(
                f"{stage} ({reason})" for stage, reason in row["resource_failures"].items())
        elif row["formal"] == "fail" and row["tests"].split("/")[0] == row["tests"].split("/")[1]:
            note = "test escape: tests pass, formal finds a difference"
        elif row["ppa_unavailable"]:
            note = "PPA unavailable: " + row["ppa_unavailable"]
        elif row["formal"] == "error" and not note:
            note = "formal: " + row["formal_message"][:45]
        if row["sim_frontend"] == "sv2v":
            note = "sv2v simulation fallback" + (f"; {note}" if note else "")
        if row["is_starter"]:
            note = f"repair starter; {note}" if note else "repair starter"
        if row.get("verification"):
            verification = row["verification"]
            note = (f"checker {verification['status']}, "
                    f"caught {verification.get('caught', 0)}/{verification.get('mutants_total', 0)} mutants, "
                    f"{verification.get('assertions', 0)} assertions, "
                    f"{verification.get('state_bits', 0)} state bits, "
                    f"{verification.get('checker_bytes', 0)} bytes")
        print(f"{row['task']:18s} {row['candidate']:30s} {row['score']:6.3f} {row['tests']:>6s} "
              f"{row['formal']:>8s} {str(row['cells']):>6s} {str(row['ref_cells']):>5s} "
              f"{row['lint_warn']:4d}  {note}")
    print(f"\n{len(rows)} candidates graded in {time.monotonic() - t0:.1f}s")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=2))
    return 0


def _turn_record(r, reward: float, info: dict) -> dict:
    return {"turn": info["turn"], "score": r.score, "reward": round(reward, 4),
            **({"verification": r.verification} if getattr(r, "verification", None) else {}),
            **({"lines_changed": info["lines_changed"]} if "lines_changed" in info else {}),
            "tests": f"{r.tests_passed}/{r.tests_total}",
            "all_tests_pass": r.all_tests_pass, "formal": r.formal_status,
            "frontend_errors": r.frontend_errors, "sim_frontend": r.sim_frontend,
            "synth_frontend": r.synth_frontend,
            "formal_frontend": r.formal_frontend, "resource_failures": r.resource_failures,
            "test_escape": r.test_escape, "inconclusive": r.inconclusive,
            "ppa_unavailable": r.ppa_unavailable,
            "solved": info["solved"],
            "cells": r.cells, "breakdown": r.breakdown,
            "timings_s": r.timings_s, "grade_s": info["grade_s"],
            "cached": r.cached}


def _usage_delta(before: dict, after: dict) -> dict:
    # A run maximum is not an additive counter. Each turn already has both token deltas.
    return {key: round(value - before.get(key, 0), 2) for key, value in after.items()
            if key != "max_context_tokens"}


def _merge_usage(total: dict, usage: dict) -> None:
    for key, value in usage.items():
        previous = total.get(key, 0)
        total[key] = max(previous, value) if key == "max_context_tokens" else round(previous + value, 2)


def _context_peak(results) -> int:
    peak = 0
    for row in results:
        usages = [row.get("usage") or {}, (row.get("shared_first") or {}).get("usage") or {}]
        usages.extend(turn.get("usage") or {} for turn in row.get("trajectory", []))
        for usage in usages:
            peak = max(peak, usage.get("max_context_tokens", 0))
            # Older local runs kept single-call token deltas without a peak field.
            # Never add episode-wide totals: they may cover several calls.
            if "ctx_truncated" in usage and usage.get("calls") == 1:
                peak = max(peak, usage.get("input_tokens", 0) + usage.get("output_tokens", 0))
    return peak


def _complete_code(action: str, code: str) -> bool:
    """A closed submitted block, or a complete module recovered by the extractor.

    Missing closing fences alone do not make recovered complete RTL truncated.
    This describes extraction, not syntax validity or acceptance.
    """
    for match in _FENCE_RE.finditer(action):
        body = match.group(2).strip()
        if body and (body == code.strip() or (
                action.strip() == code.strip()
                and re.search(r"(?m)^\s*(?:macro)?module\s+[A-Za-z_]\w*\s*(?:#|\(|;)", body))):
            return True
    # An unclosed checker fence is returned verbatim, rather than extracted.
    if _OPEN_FENCE_RE.search(code):
        return False
    # Comments and quoted diagnostics must not supply a missing endmodule.
    stripped = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/',
                      lambda m: "\n" * m.group().count("\n") or " ", code, flags=re.S)
    return _MODULE_RE.search(stripped) is not None


def _report_turn(turn: dict, usage: dict, complete_code: bool) -> dict:
    result = {**turn, "usage": dict(usage), "complete_code": complete_code}
    if usage.get("truncated", 0) > 0 and not complete_code:
        result["report_status"] = "truncated"
    return result


def _play(env: RTLEnv, agent, obs: dict, turns: list, ret: float,
          first_action: str | None = None,
          first_grade: tuple[str, EvalResult, float] | None = None,
          first_usage: dict | None = None) -> tuple[float, str | None]:
    """Run turns until the episode ends. Returns (return, error)."""
    try:
        while True:
            if first_grade is not None:
                action = first_action or first_grade[0]
                usage = first_usage or {}
                obs, reward, terminated, truncated, info = env._apply_grade(*first_grade)
                first_grade = None
                first_action = None
            else:
                if first_action is not None:
                    action, usage = first_action, first_usage or {}
                else:
                    before = dict(getattr(agent, "usage", None) or {})
                    action = agent.act(obs)
                    usage = _usage_delta(before, getattr(agent, "usage", None) or {})
                first_action = None
                obs, reward, terminated, truncated, info = env.step(action)
            ret += reward
            rec = _turn_record(info["eval"], reward, info)
            # Kept for analysis: the graded design, what the agent was shown next, and
            # the full tool report (compiler, test, formal, synthesis messages).
            rec["code"] = info.get("code")
            rec["feedback_shown"] = obs.get("feedback", "")
            rec["tool_report"] = format_feedback(info["eval"], "full")
            turns.append(_report_turn(rec, usage, _complete_code(action, rec["code"] or "")))
            if terminated or truncated:
                return ret, None
    except Exception as exc:  # noqa: BLE001 - one failed API call must not sink the run
        return ret, f"{type(exc).__name__}: {exc}"[:500]


def _episode_record(task_id: str, env: RTLEnv, turns: list, ret: float, error: str | None,
                    t0: float, usage) -> dict:
    state = env.state
    hist = state.history if state else []
    first, last = (hist[0], hist[-1]) if hist else (None, None)
    return {
        "task": task_id,
        "task_kind": state.task.kind if state else "design",
        **({"verification": last.verification}
           if last is not None and getattr(last, "verification", None) else {}),
        **({"starter_score": state.starter_score} if state and state.starter_code is not None else {}),
        "error": error,
        "truncated_attempts": sum(t.get("report_status") == "truncated" for t in turns),
        **({"report_status": "truncated"}
           if turns and turns[-1].get("report_status") == "truncated" else {}),
        "turns": len(turns),
        "pass@1": bool(first and is_solved(first)),
        "pass@1_tests_only": bool(first and first.all_tests_pass),
        "solved": bool(last and is_solved(last)),
        "test_escapes": sum(t["test_escape"] for t in turns),
        "inconclusive": sum(t["inconclusive"] for t in turns),
        "first_score": first.score if first else 0.0,
        "best_score": env.state.best_score if env.state else 0.0,
        "return": round(ret, 4),
        "wall_s": round(time.monotonic() - t0, 2),
        "trajectory": turns,
        "usage": usage,
    }


def run_episode(env_kwargs: dict, agent_name: str, agent_kwargs: dict, task_id: str) -> dict:
    env = RTLEnv(**env_kwargs)
    agent = make_agent(agent_name, **agent_kwargs)
    obs, _ = env.reset(task_id=task_id)
    agent.begin_episode(obs)
    turns: list = []
    t0 = time.monotonic()
    ret, error = _play(env, agent, obs, turns, 0.0)
    return _episode_record(task_id, env, turns, ret, error, t0, getattr(agent, "usage", None))


def run_paired_episode(env_kwargs: dict, agent_name: str, agent_kwargs: dict, task_id: str,
                       arms: tuple[str, ...] = ("full", "none")) -> dict[str, dict]:
    """One first attempt, then one branch per feedback arm from that same attempt.

    The arms share the first attempt and nothing else: every branch is forked right
    after the first act(), before any arm plays, so no arm sees another arm's
    feedback. Each arm's usage and time cover only its own turns; the shared first
    call is recorded once, under "shared_first" (identical in every arm's record)."""
    agent = make_agent(agent_name, **agent_kwargs)
    env = RTLEnv(**{**env_kwargs, "feedback": arms[0]})
    obs, _ = env.reset(task_id=task_id)
    agent.begin_episode(obs)
    t0 = time.monotonic()
    first_grade = None
    try:
        first_action, error = agent.act(obs), None
    except Exception as exc:  # noqa: BLE001
        first_action, error = None, f"{type(exc).__name__}: {exc}"[:500]
    shared = {"usage": dict(getattr(agent, "usage", None) or {}),
              "act_s": round(time.monotonic() - t0, 2), "grade_s": 0.0, "error": error}
    if first_action is not None:
        grade_started = time.monotonic()
        try:
            first_grade = env._grade(first_action)
        except Exception as exc:  # noqa: BLE001 - a shared grading error affects both arms
            error = f"{type(exc).__name__}: {exc}"[:500]
        shared["grade_s"] = round(first_grade[2] if first_grade is not None
                                  else time.monotonic() - grade_started, 3)
        shared["error"] = error
    # Fork before either arm receives its own feedback.
    branches = {arm: agent.fork() for arm in arms}
    out = {}
    for arm, branch in branches.items():
        branch_env = env._fork(arm)
        ta = time.monotonic()
        turns: list = []
        ret, err = (0.0, error) if first_action is None or error else _play(
            branch_env, branch, obs, turns, 0.0,
            first_action=first_action, first_grade=first_grade, first_usage=shared["usage"],
        )
        rec = _episode_record(task_id, branch_env, turns, ret, err, ta,
                              getattr(branch, "usage", None))
        rec["shared_first"] = shared
        out[arm] = rec
    return out


def _by_verification(rows: list[dict], formal_by_task: dict[str, bool]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        formal_enabled = formal_by_task.get(row["task"])
        if formal_enabled is not None:
            mode = "formal" if formal_enabled else "simulation_only"
            groups.setdefault(mode, []).append(row)
    return groups


def _by_kind(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row.get("task_kind", "design"), []).append(row)
    return groups


def _repair_edits(steps: list[dict]) -> dict:
    edits = [t["lines_changed"] for t in steps if "lines_changed" in t]
    accepted = [t["lines_changed"] for t in steps if t.get("solved") and "lines_changed" in t]
    return {
        "attempts": len(edits),
        "median": statistics.median(edits) if edits else None,
        "accepted_attempts": len(accepted),
        "accepted_median": statistics.median(accepted) if accepted else None,
    }


def _acceptance_counts(results: list[dict]) -> dict:
    n = len(results)
    truncated_attempts = sum(t.get("report_status") == "truncated"
                             for row in results for t in row["trajectory"])
    return {
        "tasks": sorted({r["task"] for r in results}),
        "episodes": n,
        "errors": sum(bool(r["error"]) for r in results),
        "pass@1_count": f"{sum(bool(r['pass@1']) for r in results)}/{n}",
        "solved_count": f"{sum(bool(r['solved']) for r in results)}/{n}",
        **({"truncated_attempts": truncated_attempts} if truncated_attempts else {}),
    }


def _verification_counts(results: list[dict]) -> dict:
    details = [row.get("verification") for row in results
               if row.get("report_status") != "truncated"]
    measured = [value for value in details if value]
    caught = sum(value.get("caught", 0) for value in measured)
    total = sum(value.get("mutants_total", 0) for value in measured)
    families: dict[str, dict] = {}
    for value in measured:
        for name, counts in value.get("families", {}).items():
            aggregate = families.setdefault(name, {"total": 0, "caught": 0})
            for key in aggregate:
                aggregate[key] += counts[key]
    scores = [row["trajectory"][-1]["score"] if row.get("trajectory") and not row.get("error") else 0.0
              for row in results]
    return {
        "episodes": len(results),
        "graded_episodes": len(measured),
        "false_alarm_episodes": sum(value.get("status") == "false_alarm" for value in measured),
        "invalid_episodes": sum((row.get("verification") or {}).get("status") == "invalid"
                                and row.get("report_status") != "truncated" for row in results),
        "truncated_episodes": sum(row.get("report_status") == "truncated" for row in results),
        "inconclusive_episodes": sum(value.get("status") == "inconclusive" for value in measured),
        "caught": caught,
        "mutants_total": total,
        "mutation_rate": round(caught / total, 4) if total else None,
        "mean_score": round(statistics.mean(scores), 4) if scores else None,
        "mean_weighted_caught": round(sum(value.get("weighted_caught", 0.0)
                                         for value in measured) / len(results), 4) if results else None,
        "mean_assertions": round(statistics.mean(value.get("assertions", 0) for value in measured), 2)
                           if measured else None,
        "mean_state_bits": round(statistics.mean(value.get("state_bits", 0) for value in measured), 2)
                           if measured else None,
        "mean_checker_bytes": round(statistics.mean(value.get("checker_bytes", 0) for value in measured), 2)
                              if measured else None,
        "families": families,
    }


def summarize(results: list[dict], meta: dict) -> dict:
    """Rates over ALL episodes: an episode that errored (e.g., a timeout) counts as
    unsolved, with the scores it reached before the error (0 if it never got a
    first attempt graded), instead of silently dropping out of the denominator."""
    n = len(results)
    ok = [r for r in results if not r["error"]]

    def frac(key):
        return round(sum(bool(r[key]) for r in results) / n, 3) if n else None

    def count(key):
        return f"{sum(bool(r[key]) for r in results)}/{n}"

    def mean(key):
        return round(sum(r[key] for r in results) / n, 3) if n else None

    grade = [t["grade_s"] for r in results for t in r["trajectory"] if not t["cached"]]
    steps = [t for r in results for t in r["trajectory"]]
    usage: dict[str, float] = {}
    for r in results:
        _merge_usage(usage, r.get("usage") or {})
    context_peak = _context_peak(results)
    formal_by_task = meta.get("formal_by_task") or {}
    per_task = {}
    for tid in sorted({r["task"] for r in results}):
        rs = [r for r in results if r["task"] == tid]
        per_task[tid] = {"episodes": len(rs),
                         "errors": sum(bool(r["error"]) for r in rs),
                         "pass@1": round(sum(r["pass@1"] for r in rs) / len(rs), 3),
                         "solved": round(sum(r["solved"] for r in rs) / len(rs), 3),
                         "pass@1_count": f"{sum(r['pass@1'] for r in rs)}/{len(rs)}",
                         "solved_count": f"{sum(r['solved'] for r in rs)}/{len(rs)}",
                         "mean_turns": round(sum(r["turns"] for r in rs) / len(rs), 2)}
        truncated_attempts = sum(t.get("report_status") == "truncated"
                                 for row in rs for t in row["trajectory"])
        if truncated_attempts:
            per_task[tid]["truncated_attempts"] = truncated_attempts
        if tid in formal_by_task:
            per_task[tid]["formal_enabled"] = formal_by_task[tid]
        kind = rs[0].get("task_kind", "design")
        if kind == "repair":
            per_task[tid]["task_kind"] = kind
            per_task[tid]["lines_changed"] = _repair_edits([t for r in rs for t in r["trajectory"]])
        elif kind == "verify":
            per_task[tid]["task_kind"] = kind
            per_task[tid]["verification"] = _verification_counts(rs)
    by_verification = {mode: _acceptance_counts(group)
                       for mode, group in _by_verification(results, formal_by_task).items()}
    by_kind = {kind: _acceptance_counts(group) for kind, group in _by_kind(results).items()}
    if "repair" in by_kind:
        by_kind["repair"]["lines_changed"] = _repair_edits(
            [t for r in results if r.get("task_kind") == "repair" for t in r["trajectory"]]
        )
    if "verify" in by_kind:
        by_kind["verify"]["verification"] = _verification_counts(
            [row for row in results if row.get("task_kind") == "verify"]
        )
    return {
        **meta,
        "by_verification": by_verification,
        "by_kind": by_kind,
        "episodes": n,
        "errors": n - len(ok),
        "pass@1": frac("pass@1"),
        "pass@1_count": count("pass@1"),
        "pass@1_ci95": clopper_pearson(sum(bool(r["pass@1"]) for r in results), n),
        "pass@1_tests_only": frac("pass@1_tests_only"),
        "solved_within_turns": frac("solved"),
        "solved_count": count("solved"),
        "solved_within_turns_ci95": clopper_pearson(sum(bool(r["solved"]) for r in results), n),
        "test_escape_attempts": sum(r["test_escapes"] for r in results),
        "inconclusive_attempts": sum(r.get("inconclusive", 0) for r in results),
        "frontend_failure_attempts": sum(bool(t.get("frontend_errors"))
                                         and t.get("report_status") != "truncated" for t in steps),
        "sim_frontend_fallback_attempts": sum(t.get("sim_frontend") == "sv2v" for t in steps),
        "resource_failure_attempts": sum(bool(t.get("resource_failures")) for t in steps),
        "truncated_attempts": sum(t.get("report_status") == "truncated" for t in steps),
        "mean_first_score": mean("first_score"),
        "mean_best_score": mean("best_score"),
        "mean_turns": mean("turns"),
        "grading_s_p50": round(statistics.median(grade), 3) if grade else None,
        "grading_s_p95": (round(statistics.quantiles(grade, n=20)[-1], 3)
                          if len(grade) >= 2 else (grade[0] if grade else None)),
        "cache_hit_rate": round(sum(t["cached"] for t in steps) / len(steps), 3) if steps else None,
        "usage": usage,
        **({"max_context_tokens": context_peak} if context_peak else {}),
        "per_task": per_task,
    }


def refresh_report(data: dict) -> dict:
    """Refresh reporting causes in memory, leaving archived grades and bytes alone.

    Old one-turn runs have unambiguous per-call usage. Old multi-turn totals do
    not identify the cut-off turn, so they are never assigned to an attempt.
    """
    if not data.get("episodes"):
        return data
    episodes = []
    for original in data["episodes"]:
        turns = []
        old_turns = original.get("trajectory", [])
        for turn in old_turns:
            usage = turn.get("usage")
            if usage is None and len(old_turns) == 1:
                shared = original.get("shared_first")
                usage = ((shared or {}).get("usage") if shared else original.get("usage")) or {}
            if usage is not None:
                code = turn.get("code")
                complete = turn.get("complete_code")
                if complete is None and code is not None:
                    complete = _complete_code(code, code)
                if complete is not None:
                    turn = _report_turn(turn, usage, complete)
            turns.append(turn)
        episode = {**original, "trajectory": turns,
                   "truncated_attempts": sum(t.get("report_status") == "truncated" for t in turns)}
        if turns and turns[-1].get("report_status") == "truncated":
            episode["report_status"] = "truncated"
        episodes.append(episode)
    result = {**data, "episodes": episodes}
    required = {"task", "error", "trajectory", "pass@1", "pass@1_tests_only", "solved",
                "turns", "test_escapes", "first_score", "best_score"}
    if "summary" in data and all(required <= row.keys() for row in episodes):
        result["summary"] = summarize(episodes, data["summary"])
    return result


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar test: a binomial test of b successes out of b + c
    discordant pairs, with p = 1/2. Returns 1.0 when there are no discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def _paired_counts(rows: list[dict], a: str, b: str) -> dict:
    totals = dict.fromkeys(("both", f"only_{a}", f"only_{b}", "neither", "errored"), 0)
    for row in rows:
        totals[row["outcome"]] += 1
    only_a, only_b = totals[f"only_{a}"], totals[f"only_{b}"]
    return {
        "episodes": len(rows),
        "outcomes": totals,
        "informative_episodes": sum(row["outcome"] != "errored" and not row["first_attempt_solved"]
                                    for row in rows),
        "discordant_pairs": only_a + only_b,
        "mcnemar_exact_p": mcnemar_exact(only_a, only_b),
    }


def paired_table(per_arm: dict[str, list[dict]], arms: tuple[str, str],
                 formal_by_task: dict[str, bool] | None = None) -> dict:
    """Per-task outcomes of paired episodes (same first attempt in both arms).

    An episode whose shared first attempt failed (e.g., an API error) has no
    outcome in either arm: it is counted as "errored" and left out of the other
    counts and the test. An episode whose first attempt was accepted cannot differ
    between the arms, so only the "informative" ones (first attempt not accepted)
    can become discordant pairs."""
    a, b = arms
    rows = []
    for ra, rb in zip(per_arm[a], per_arm[b], strict=True):
        if (ra.get("shared_first") or {}).get("error"):
            key = "errored"
        else:
            key = ("both" if ra["solved"] and rb["solved"] else f"only_{a}" if ra["solved"]
                   else f"only_{b}" if rb["solved"] else "neither")
        rows.append({"task": ra["task"], "task_kind": ra.get("task_kind", "design"),
                     "first_attempt_solved": ra["pass@1"],
                     f"{a}_solved": ra["solved"], f"{b}_solved": rb["solved"],
                     f"{a}_best": ra["best_score"], f"{b}_best": rb["best_score"],
                     f"{a}_error": ra["error"], f"{b}_error": rb["error"],
                     "outcome": key})
    shared: dict[str, float] = {"act_s": 0.0}
    for r in per_arm[a]:
        first = r.get("shared_first") or {}
        shared["act_s"] = round(shared["act_s"] + first.get("act_s", 0.0), 2)
        if "grade_s" in first:
            shared["grade_s"] = round(shared.get("grade_s", 0.0) + first["grade_s"], 3)
        _merge_usage(shared, first.get("usage") or {})
    context_peak = _context_peak(row for arm in arms for row in per_arm[arm])
    by_verification = {mode: _paired_counts(group, a, b)
                       for mode, group in _by_verification(rows, formal_by_task or {}).items()}
    by_kind = {kind: _paired_counts(group, a, b) for kind, group in _by_kind(rows).items()}
    return {"arms": list(arms), **_paired_counts(rows, a, b), "by_verification": by_verification,
            "by_kind": by_kind, "shared_first": shared,
            **({"max_context_tokens": context_peak} if context_peak else {}), "rows": rows}


def cmd_run(args) -> int:
    if args.paired and args.feedback:
        sys.exit("--paired runs both the 'full' and 'none' arms; leave out --feedback")
    args.feedback = args.feedback or "full"
    env_kwargs = dict(tasks_root=args.tasks_root, max_turns=args.max_turns,
                      reward_mode=args.reward_mode, feedback=args.feedback,
                      use_cache=not args.no_cache, use_formal=not args.no_formal)
    agent_kwargs: dict = {}
    if args.agent == "replay":
        agent_kwargs["tasks_root"] = args.tasks_root
    elif args.agent == "ollama":
        if not args.model:
            sys.exit("--agent ollama needs --model (an installed model, e.g. qwen3:14b)")
        if args.effort:
            sys.exit("--effort applies to the Claude agent only")
        agent_kwargs.update(model=args.model, host=args.ollama_host,
                            timeout_s=args.ollama_timeout, num_ctx=args.num_ctx)
        if args.max_tokens:
            agent_kwargs["max_tokens"] = args.max_tokens
        if args.think != "default":
            agent_kwargs["think"] = args.think == "on"
        if args.seed is not None:
            agent_kwargs["seed"] = args.seed
    else:
        if args.model:
            agent_kwargs["model"] = args.model
        if args.effort:
            agent_kwargs["effort"] = args.effort
        if args.max_tokens:
            agent_kwargs["max_tokens"] = args.max_tokens
    if args.seed is not None and args.agent != "ollama":
        sys.exit("--seed applies to --agent ollama only")
    ids = _tasks_arg(args.tasks, args.tasks_root)
    if args.no_formal and any(load_task(tid, args.tasks_root).kind == "verify" for tid in ids):
        sys.exit("verification tasks require their formal checker run")
    formal_by_task = {tid: not args.no_formal and load_task(tid, args.tasks_root).has_formal for tid in ids}
    episodes = [tid for tid in ids for _ in range(args.samples)]

    def kwargs_for(i: int) -> dict:
        # A fixed seed would make every sample of a task identical: offset it per episode.
        if "seed" in agent_kwargs:
            return {**agent_kwargs, "seed": agent_kwargs["seed"] + i}
        return agent_kwargs

    arms = ("full", "none")
    if args.paired and not args.out:
        sys.exit("--paired needs --out (one file per arm plus a paired summary)")
    started = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        if args.paired:
            pairs = list(pool.map(lambda j: run_paired_episode(
                env_kwargs, args.agent, kwargs_for(j[0]), j[1], arms), enumerate(episodes)))
            per_arm = {arm: [p[arm] for p in pairs] for arm in arms}
        else:
            per_arm = {args.feedback: list(pool.map(lambda j: run_episode(
                env_kwargs, args.agent, kwargs_for(j[0]), j[1]), enumerate(episodes)))}
    for arm, results in per_arm.items():
        if args.paired:
            print(f"\n--- feedback arm: {arm}")
        _print_episodes(results)
    meta = {
        "agent": args.agent,
        "model": (args.model or os.environ.get("RTLGYM_MODEL", DEFAULT_MODEL))
                 if args.agent != "replay" else None,
        "effort": args.effort,
        "samples_per_task": args.samples,
        "max_turns": args.max_turns,
        "feedback": args.feedback,
        "reward_mode": args.reward_mode,
        "formal": not args.no_formal,
        "formal_by_task": formal_by_task,
        "tasks": ids,
        "started_utc": started,
        "wall_s": None,
        "git_commit": _git_commit(),
        "python": platform.python_version(),
        "tools": tool_versions(),
    }
    if args.seed is not None:
        meta["seed"] = {"base": args.seed, "per_episode": "base + episode index"}
    if args.agent == "ollama":
        from .agents.ollama import OllamaAgent, model_info
        probe = OllamaAgent(**agent_kwargs)   # what each episode's agent actually sends
        meta["ollama"] = {**probe.settings(), "build": model_info(probe.model, probe.host)}
    wall = round(time.monotonic() - t0, 2)
    summaries = {}
    for arm, results in per_arm.items():
        extra = {"feedback": arm, "paired": True, "pair_arms": list(arms)} if args.paired else {}
        summaries[arm] = summarize(results, {**meta, **extra})
        summaries[arm]["wall_s"] = wall   # the whole run (arms of a pair run together)
        if args.paired:
            # This arm's own turns (after the shared first attempt), summed over episodes.
            summaries[arm]["arm_s"] = round(sum(r["wall_s"] for r in results), 2)
            summaries[arm]["shared_first_s"] = round(
                sum((r.get("shared_first") or {}).get("act_s", 0.0) for r in results), 2)
        print("\n" + json.dumps({k: v for k, v in summaries[arm].items()
                                 if k not in ("per_task", "tasks", "formal_by_task")}, indent=2))
    if args.paired:
        paired = paired_table(per_arm, arms, formal_by_task)
        _print_paired(paired)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        if args.paired:
            for arm in arms:
                _write_json(out.with_name(f"{out.stem}__{arm}.json"),
                            {"summary": summaries[arm], "episodes": per_arm[arm]})
            _write_json(out.with_name(f"{out.stem}__paired.json"),
                        {"paired": paired, "meta": {**meta, "wall_s": wall}})
        else:
            _write_json(out, {"summary": summaries[args.feedback],
                              "episodes": per_arm[args.feedback]})
    total = sum(len(r) for r in per_arm.values())
    errors = sum(s["errors"] for s in summaries.values())
    return 1 if errors == total else 0


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, default=str))


def _print_episodes(results: list[dict]) -> None:
    print(f"{'task':18s} {'turns':>5s} {'pass@1':>6s} {'solved':>6s} {'first':>6s} {'best':>6s}"
          f"  per-turn scores")
    for r in results:
        scores = " -> ".join("truncated" if t.get("report_status") == "truncated"
                            else f"{t['score']:.2f}" for t in r["trajectory"])
        if r["error"]:
            print(f"{r['task']:18s} ERROR {r['error'][:90]}" + (f"  (after {scores})"
                                                                 if scores else ""))
            continue
        print(f"{r['task']:18s} {r['turns']:5d} {str(r['pass@1']):>6s} {str(r['solved']):>6s} "
              f"{r['first_score']:6.3f} {r['best_score']:6.3f}  {scores}")


def _verification_label(mode: str) -> str:
    return {"formal": "Formal enabled", "simulation_only": "Simulation only"}[mode]


def _print_paired(p: dict) -> None:
    a, b = p["arms"]
    groups = [("All tasks", p)]
    groups.extend((_verification_label(mode), group)
                  for mode, group in sorted(p.get("by_verification", {}).items()))
    print("\nPaired outcomes (same first attempt in both arms):")
    for label, group in groups:
        o = group["outcomes"]
        print(f"  {label}: {group['episodes']} episodes, solved in both: {o['both']}, "
              f"only with {a}: {o[f'only_{a}']}, only with {b}: {o[f'only_{b}']}, "
              f"in neither: {o['neither']}, errored before a first attempt: {o['errored']}")
        print(f"  {group['informative_episodes']} informative episode(s) (first attempt not accepted), "
              f"{group['discordant_pairs']} discordant pair(s), exact McNemar p = "
              f"{group['mcnemar_exact_p']}.")


def _pct(v) -> str:
    return "n/a" if v is None else f"{100 * v:.0f}%"


def _grading(s: dict) -> str:
    if s.get("grading_s_p50") is None:
        return "n/a (all cached)"
    return f"{s['grading_s_p50']} s / {s['grading_s_p95']} s"


def _count(rate, n: int) -> str:
    """'2/8 (25%)': raw counts with the denominator, not just a percentage."""
    if rate is None:
        return "n/a"
    return f"{round(rate * n)}/{n} ({_pct(rate)})"


def _arm(s: dict) -> str:
    name = s.get("model") or s.get("agent")
    parts = [f"feedback {s.get('feedback', 'full')}"]
    if s.get("effort"):
        parts.append(f"effort {s['effort']}")
    if not s.get("formal", True):
        parts.append("no formal")
    if s.get("paired"):
        parts.append("paired")
    return f"{name} ({', '.join(parts)})"


def _print_verify_results(runs: list[dict]) -> None:
    if not any("verify" in summary.get("by_kind", {}) for summary in runs):
        return
    print("\n### Verification checker results\n")
    print("| Arm | Episodes (graded) | False alarms | Invalid | Truncated | Inconclusive | "
          "Mutants caught | Mean family coverage | Mean reward |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for summary in runs:
        group = summary.get("by_kind", {}).get("verify")
        if group is None:
            continue
        counts = group["verification"]
        print(f"| {_arm(summary)} | {counts['episodes']} ({counts['graded_episodes']}) | "
              f"{counts['false_alarm_episodes']} | {counts['invalid_episodes']} | "
              f"{counts.get('truncated_episodes', 0)} | "
              f"{counts['inconclusive_episodes']} | {counts['caught']}/{counts['mutants_total']} | "
              f"{_pct(counts['mean_weighted_caught'])} | {counts['mean_score']} |")
    print("\nEach episode contributes its final checker. Mutant counts are checks across episodes. "
          "Family coverage weights mutation families equally. False alarms, invalid checkers, "
          "truncated outputs, inconclusive grades and episodes with errors earn zero reward.")
    print("\n| Arm | Mean assertions | Mean state bits | Mean source bytes |")
    print("|---|---:|---:|---:|")
    for summary in runs:
        group = summary.get("by_kind", {}).get("verify")
        if group is not None:
            counts = group["verification"]
            print(f"| {_arm(summary)} | {counts.get('mean_assertions', 'n/a')} | "
                  f"{counts.get('mean_state_bits', 'n/a')} | {counts.get('mean_checker_bytes', 'n/a')} |")


def cmd_report(args) -> int:
    """Turn one or more `run --out` files into Markdown tables."""
    data = [refresh_report(json.loads(Path(f).read_text())) for f in args.files]
    runs = [d["summary"] for d in data if "summary" in d]      # skip paired summaries
    print("| Arm | Episodes (errors) | Accepted on 1st attempt | 1st attempt passes tests "
          "| Accepted within N turns | Test escapes | Inconclusive | Truncated attempts | Mean turns "
          "| Grading p50 / p95 | First-attempt 95% CI | Within-turn 95% CI |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in runs:
        n = s["episodes"]
        print(f"| {_arm(s)} | {n} ({s['errors']}) | "
              f"{_count(s['pass@1'], n)} | {_count(s['pass@1_tests_only'], n)} | "
              f"{_count(s['solved_within_turns'], n)} (N={s['max_turns']}) | "
              f"{s['test_escape_attempts']} | {s.get('inconclusive_attempts', 0)} | "
              f"{s.get('truncated_attempts', 0)} | {s['mean_turns']} | {_grading(s)} | "
              f"{format_ci(s.get('pass@1_ci95'))} | "
              f"{format_ci(s.get('solved_within_turns_ci95'))} |")
    print("\n95% Clopper-Pearson intervals include every episode, including errors. "
          "Each feedback arm is reported separately. These binomial intervals describe "
          "the sampled episodes and do not account for task clustering or multiple comparisons.")
    _print_verify_results(runs)
    if any(s.get("by_verification") for s in runs):
        print("\n### Acceptance by verification mode\n")
        print("| Arm | Verification | Episodes (errors) | First attempt | Within turn budget |")
        print("|---|---|---:|---:|---:|")
        for s in runs:
            for mode, group in sorted(s.get("by_verification", {}).items()):
                print(f"| {_arm(s)} | {_verification_label(mode)} | "
                      f"{group['episodes']} ({group['errors']}) | "
                      f"{group['pass@1_count']} | {group['solved_count']} |")
    tasks = sorted({t for s in runs for t in s["per_task"]})
    print()
    print("| Task | " + " | ".join(_arm(s) for s in runs) + " |")
    print("|---|" + "---:|" * len(runs))
    for t in tasks:
        cells = []
        for s in runs:
            pt = s["per_task"].get(t)
            if not pt:
                cells.append("n/a")
                continue
            simulation_only = pt.get("formal_enabled", s.get("formal")) is False
            label = " (simulation only)" if simulation_only else ""
            if pt.get("truncated_attempts"):
                label += f"; {pt['truncated_attempts']} truncated"
            cells.append(f"{_count(pt['pass@1'], pt['episodes'])} → "
                         f"{_count(pt['solved'], pt['episodes'])}{label}")
        print(f"| {t} | " + " | ".join(cells) + " |")
    print()
    turns = sorted({s["max_turns"] for s in runs})
    if len(turns) > 1:
        print(f"Note: the runs use different turn budgets ({turns}); compare rates with care.")
    first = runs[0]
    if any("verify" in summary.get("by_kind", {}) for summary in runs):
        print("Per-task cells: accepted on the first attempt → accepted within the turn budget. "
              "A verification checker is accepted after passing the good-design checks and "
              "catching every included mutant. "
              f"Commit {first['git_commit'][:7]}; {first['tools'].get('yosys', '')}.")
    else:
        print(f"Per-task cells: accepted on the first attempt → accepted within the turn budget. "
              f"Accepted means every hidden test passed, the design synthesized without latches, "
              f"and the formal check passed where enabled. Commit {first['git_commit'][:7]}; "
              f"{first['tools'].get('yosys', '')}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rtlgym", description=__doc__)
    ap.add_argument("--tasks-root", type=Path, default=DEFAULT_TASKS_ROOT)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="list tasks")
    p.add_argument("--tasks", default="all", help=_TASKS_HELP)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("score", help="grade one RTL file against one task")
    p.add_argument("task")
    p.add_argument("file")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--no-formal", action="store_true", help="skip the formal equivalence check")
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("baselines", help="grade the reference and all hand-written candidates")
    p.add_argument("--tasks", default="all", help=_TASKS_HELP)
    p.add_argument("--workers", type=_positive_int, default=4)
    p.add_argument("--out")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--no-formal", action="store_true")
    p.set_defaults(fn=cmd_baselines)

    p = sub.add_parser("run", help="run multi-turn episodes with an agent")
    p.add_argument("--agent", choices=["replay", "claude", "ollama"], default="replay")
    p.add_argument("--model", help="Claude model ID (default: $RTLGYM_MODEL or claude-sonnet-5-5); "
                                    "with --agent ollama, a local model name such as qwen3:14b")
    p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                   help="Claude effort level (default: the model's own default)")
    p.add_argument("--max-tokens", type=_positive_int,
                   help="output token limit per call, thinking included "
                        "(default: the model's own for Claude; 8192 for --agent ollama)")
    p.add_argument("--tasks", default="all", help=_TASKS_HELP)
    p.add_argument("--samples", type=_positive_int, default=1, help="episodes per task")
    p.add_argument("--paired", action="store_true",
                   help="grade one first attempt per episode, then branch it into the 'full' "
                        "and 'none' feedback arms (a paired comparison); writes "
                        "OUT__full.json, OUT__none.json, and OUT__paired.json")
    p.add_argument("--max-turns", type=_positive_int, default=3)
    p.add_argument("--reward-mode", choices=["improvement", "score"], default="improvement")
    p.add_argument("--feedback", choices=["none", "summary", "full"],
                   help="what the agent sees between attempts (default: full); "
                        "not used with --paired, which runs 'full' and 'none'")
    p.add_argument("--workers", type=_positive_int, default=4)
    p.add_argument("--out")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--no-formal", action="store_true")
    g = p.add_argument_group("local models (--agent ollama)")
    g.add_argument("--ollama-host", help="Ollama URL (default: $OLLAMA_HOST or "
                                         "http://localhost:11434)")
    g.add_argument("--ollama-timeout", type=float, default=1800.0,
                   help="seconds to wait for one reply (default 1800; local models are slow)")
    g.add_argument("--num-ctx", type=_positive_int, default=16384,
                   help="context window in tokens (Ollama's default is too small for "
                        "multi-turn episodes)")
    g.add_argument("--think", choices=["default", "on", "off"], default="default",
                   help="reasoning mode for models that support it, e.g. Qwen3 "
                        "(default: the model's own setting; ignored for models without one)")
    g.add_argument("--seed", type=int, help="sampling seed passed to Ollama")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("report", help="summarize `run --out` result files as Markdown")
    p.add_argument("files", nargs="+")
    p.set_defaults(fn=cmd_report)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
