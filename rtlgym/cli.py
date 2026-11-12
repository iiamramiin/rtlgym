# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Command-line entry point: python -m rtlgym <command>."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .agents import make_agent
from .agents.claude import DEFAULT_MODEL
from .env import RTLEnv, format_feedback, is_solved
from .evaluator import evaluate
from .task import DEFAULT_TASKS_ROOT, list_tasks, load_task
from .tools import tool_versions

REPO_ROOT = Path(__file__).resolve().parent.parent


def _tasks_arg(value: str, root: Path) -> list[str]:
    all_ids = list_tasks(root)
    if value == "all":
        return all_ids
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


def _git_commit() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def cmd_list(args) -> int:
    for tid in list_tasks(args.tasks_root):
        t = load_task(tid, args.tasks_root)
        fv = f"formal depth {t.formal.get('depth')}" if t.has_formal else "no formal"
        print(f"{tid:20s} {t.difficulty:8s} {fv:16s} {', '.join(t.tags)}")
    return 0


def cmd_score(args) -> int:
    task = load_task(args.task, args.tasks_root)
    code = Path(args.file).read_text()
    res = evaluate(task, code, use_cache=not args.no_cache, use_formal=not args.no_formal)
    print(format_feedback(res, "full"))
    print(json.dumps({"score": res.score, "breakdown": res.breakdown,
                      "formal": res.formal_status, "timings_s": res.timings_s}, indent=2))
    return 0


def cmd_baselines(args) -> int:
    """Score the reference and every hand-written candidate: a sanity check that
    the reward ranks known-good above known-bad and blocks known hacks."""
    rows = []
    jobs = []
    for tid in _tasks_arg(args.tasks, args.tasks_root):
        task = load_task(tid, args.tasks_root)
        for path in [task.ref_path, *task.candidates()]:
            jobs.append((task, path))
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda j: evaluate(j[0], j[1].read_text(),
                                                   use_cache=not args.no_cache,
                                                   use_formal=not args.no_formal), jobs))
    for (task, path), r in zip(jobs, results, strict=True):
        name = "ref.sv" if path == task.ref_path else path.name
        rows.append({"task": task.id, "candidate": name, "score": r.score,
                     "tests": f"{r.tests_passed}/{r.tests_total}", "formal": r.formal_status,
                     "formal_message": r.formal_message,
                     "compile": r.compile_ok, "lint_warn": len(r.lint_warnings),
                     "cells": r.cells, "ref_cells": r.ref_cells, "depth": r.depth,
                     "violations": r.violations, "breakdown": r.breakdown})
    print(f"{'task':18s} {'candidate':30s} {'score':>6s} {'tests':>6s} {'formal':>8s} "
          f"{'cells':>6s} {'ref':>5s} {'warn':>4s}  note")
    for row in rows:
        note = "; ".join(row["violations"])[:50] or ("" if row["compile"] else "compile error")
        if row["formal"] == "fail" and row["tests"].split("/")[0] == row["tests"].split("/")[1]:
            note = "test escape: tests pass, formal finds a difference"
        elif row["formal"] == "error" and not note:
            note = "formal: " + row["formal_message"][:45]
        print(f"{row['task']:18s} {row['candidate']:30s} {row['score']:6.3f} {row['tests']:>6s} "
              f"{row['formal']:>8s} {str(row['cells']):>6s} {str(row['ref_cells']):>5s} "
              f"{row['lint_warn']:4d}  {note}")
    print(f"\n{len(rows)} candidates graded in {time.monotonic() - t0:.1f}s")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=2))
    return 0


def run_episode(env_kwargs: dict, agent_name: str, agent_kwargs: dict, task_id: str) -> dict:
    env = RTLEnv(**env_kwargs)
    agent = make_agent(agent_name, **agent_kwargs)
    obs, _ = env.reset(task_id=task_id)
    agent.begin_episode(obs)
    turns, ret, t0 = [], 0.0, time.monotonic()
    error = None
    try:
        while True:
            action = agent.act(obs)
            obs, reward, terminated, truncated, info = env.step(action)
            r = info["eval"]
            ret += reward
            turns.append({"turn": info["turn"], "score": r.score, "reward": round(reward, 4),
                          "tests": f"{r.tests_passed}/{r.tests_total}",
                          "all_tests_pass": r.all_tests_pass, "formal": r.formal_status,
                          "test_escape": r.test_escape, "inconclusive": r.inconclusive,
                          "solved": info["solved"],
                          "cells": r.cells, "breakdown": r.breakdown,
                          "timings_s": r.timings_s, "grade_s": info["grade_s"],
                          "cached": r.cached})
            if terminated or truncated:
                break
    except Exception as exc:  # noqa: BLE001 - one failed API call must not sink the run
        error = f"{type(exc).__name__}: {exc}"[:500]
    hist = env.state.history if env.state else []
    first, last = (hist[0], hist[-1]) if hist else (None, None)
    return {
        "task": task_id,
        "error": error,
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
        "usage": getattr(agent, "usage", None),
    }


def summarize(results: list[dict], meta: dict) -> dict:
    ok = [r for r in results if not r["error"]]
    n = len(ok)

    def frac(key):
        return round(sum(bool(r[key]) for r in ok) / n, 3) if n else None

    def mean(key):
        return round(sum(r[key] for r in ok) / n, 3) if n else None

    grade = [t["grade_s"] for r in ok for t in r["trajectory"] if not t["cached"]]
    steps = [t for r in ok for t in r["trajectory"]]
    usage: dict[str, int] = {}
    for r in ok:
        for k, v in (r.get("usage") or {}).items():
            usage[k] = usage.get(k, 0) + v
    per_task = {}
    for tid in sorted({r["task"] for r in ok}):
        rs = [r for r in ok if r["task"] == tid]
        per_task[tid] = {"episodes": len(rs),
                         "pass@1": round(sum(r["pass@1"] for r in rs) / len(rs), 3),
                         "solved": round(sum(r["solved"] for r in rs) / len(rs), 3),
                         "mean_turns": round(sum(r["turns"] for r in rs) / len(rs), 2)}
    return {
        **meta,
        "episodes": len(results),
        "errors": len(results) - n,
        "pass@1": frac("pass@1"),
        "pass@1_tests_only": frac("pass@1_tests_only"),
        "solved_within_turns": frac("solved"),
        "test_escape_attempts": sum(r["test_escapes"] for r in ok),
        "inconclusive_attempts": sum(r.get("inconclusive", 0) for r in ok),
        "mean_first_score": mean("first_score"),
        "mean_best_score": mean("best_score"),
        "mean_turns": mean("turns"),
        "grading_s_p50": round(statistics.median(grade), 3) if grade else None,
        "grading_s_p95": (round(statistics.quantiles(grade, n=20)[-1], 3)
                          if len(grade) >= 2 else (grade[0] if grade else None)),
        "cache_hit_rate": round(sum(t["cached"] for t in steps) / len(steps), 3) if steps else None,
        "usage": usage,
        "per_task": per_task,
    }


def cmd_run(args) -> int:
    env_kwargs = dict(tasks_root=args.tasks_root, max_turns=args.max_turns,
                      reward_mode=args.reward_mode, feedback=args.feedback,
                      use_cache=not args.no_cache, use_formal=not args.no_formal)
    agent_kwargs: dict = {}
    if args.agent == "replay":
        agent_kwargs["tasks_root"] = args.tasks_root
    else:
        if args.model:
            agent_kwargs["model"] = args.model
        if args.effort:
            agent_kwargs["effort"] = args.effort
        if args.max_tokens:
            agent_kwargs["max_tokens"] = args.max_tokens
    ids = _tasks_arg(args.tasks, args.tasks_root)
    episodes = [tid for tid in ids for _ in range(args.samples)]
    started = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda tid: run_episode(env_kwargs, args.agent, agent_kwargs,
                                                        tid), episodes))
    print(f"{'task':18s} {'turns':>5s} {'pass@1':>6s} {'solved':>6s} {'first':>6s} {'best':>6s}"
          f"  per-turn scores")
    for r in results:
        if r["error"]:
            print(f"{r['task']:18s} ERROR {r['error'][:90]}")
            continue
        scores = " -> ".join(f"{t['score']:.2f}" for t in r["trajectory"])
        print(f"{r['task']:18s} {r['turns']:5d} {str(r['pass@1']):>6s} {str(r['solved']):>6s} "
              f"{r['first_score']:6.3f} {r['best_score']:6.3f}  {scores}")
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
        "tasks": ids,
        "started_utc": started,
        "wall_s": None,
        "git_commit": _git_commit(),
        "python": platform.python_version(),
        "tools": tool_versions(),
    }
    summary = summarize(results, meta)
    summary["wall_s"] = round(time.monotonic() - t0, 2)
    print("\n" + json.dumps({k: v for k, v in summary.items() if k not in ("per_task", "tasks")},
                            indent=2))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"summary": summary, "episodes": results}, indent=2,
                                  default=str))
    return 1 if summary["errors"] == len(results) else 0


def _pct(v) -> str:
    return "n/a" if v is None else f"{100 * v:.0f}%"


def _arm(s: dict) -> str:
    name = s.get("model") or s.get("agent")
    parts = [f"feedback {s.get('feedback', 'full')}"]
    if s.get("effort"):
        parts.append(f"effort {s['effort']}")
    if not s.get("formal", True):
        parts.append("no formal")
    return f"{name} ({', '.join(parts)})"


def cmd_report(args) -> int:
    """Turn one or more `run --out` files into Markdown tables."""
    runs = [json.loads(Path(f).read_text())["summary"] for f in args.files]
    print("| Arm | Episodes ok / run | Accepted on 1st attempt | 1st attempt passes tests "
          "| Accepted within N turns | Test escapes | Inconclusive | Mean turns "
          "| Grading p50 / p95 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in runs:
        print(f"| {_arm(s)} | {s['episodes'] - s['errors']} / {s['episodes']} | "
              f"{_pct(s['pass@1'])} | {_pct(s['pass@1_tests_only'])} | "
              f"{_pct(s['solved_within_turns'])} (N={s['max_turns']}) | "
              f"{s['test_escape_attempts']} | {s.get('inconclusive_attempts', 0)} | "
              f"{s['mean_turns']} | {s['grading_s_p50']} s / {s['grading_s_p95']} s |")
    tasks = sorted({t for s in runs for t in s["per_task"]})
    print()
    print("| Task | " + " | ".join(_arm(s) for s in runs) + " |")
    print("|---|" + "---:|" * len(runs))
    for t in tasks:
        cells = []
        for s in runs:
            pt = s["per_task"].get(t)
            cells.append("n/a" if not pt else f"{_pct(pt['pass@1'])} → {_pct(pt['solved'])}")
        print(f"| {t} | " + " | ".join(cells) + " |")
    print()
    turns = sorted({s["max_turns"] for s in runs})
    if len(turns) > 1:
        print(f"Note: the runs use different turn budgets ({turns}); compare rates with care.")
    first = runs[0]
    print(f"Per-task cells: accepted on the first attempt → accepted within the turn budget. "
          f"Accepted means every hidden test passed, the design synthesized without latches, "
          f"and the formal check passed. Commit {first['git_commit'][:7]}; "
          f"{first['tools'].get('yosys', '')}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rtlgym", description=__doc__)
    ap.add_argument("--tasks-root", type=Path, default=DEFAULT_TASKS_ROOT)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list tasks").set_defaults(fn=cmd_list)

    p = sub.add_parser("score", help="grade one RTL file against one task")
    p.add_argument("task")
    p.add_argument("file")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--no-formal", action="store_true", help="skip the formal equivalence check")
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("baselines", help="grade the reference and all hand-written candidates")
    p.add_argument("--tasks", default="all")
    p.add_argument("--workers", type=_positive_int, default=4)
    p.add_argument("--out")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--no-formal", action="store_true")
    p.set_defaults(fn=cmd_baselines)

    p = sub.add_parser("run", help="run multi-turn episodes with an agent")
    p.add_argument("--agent", choices=["replay", "claude"], default="replay")
    p.add_argument("--model", help="Claude model ID (default: $RTLGYM_MODEL or claude-sonnet-5-5)")
    p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                   help="Claude effort level (default: the model's own default)")
    p.add_argument("--max-tokens", type=_positive_int,
                   help="output token limit per call, thinking included")
    p.add_argument("--tasks", default="all")
    p.add_argument("--samples", type=_positive_int, default=1, help="episodes per task")
    p.add_argument("--max-turns", type=_positive_int, default=3)
    p.add_argument("--reward-mode", choices=["improvement", "score"], default="improvement")
    p.add_argument("--feedback", choices=["none", "summary", "full"], default="full")
    p.add_argument("--workers", type=_positive_int, default=4)
    p.add_argument("--out")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--no-formal", action="store_true")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("report", help="summarize `run --out` result files as Markdown")
    p.add_argument("files", nargs="+")
    p.set_defaults(fn=cmd_report)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
