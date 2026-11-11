# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Command-line entry point: python -m rtlgym <command>."""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .agents import make_agent
from .env import RTLEnv, format_feedback
from .evaluator import evaluate
from .task import DEFAULT_TASKS_ROOT, list_tasks, load_task
from .tools import tool_versions


def _tasks_arg(value: str, root: Path) -> list[str]:
    all_ids = list_tasks(root)
    if value == "all":
        return all_ids
    ids = [t.strip() for t in value.split(",") if t.strip()]
    unknown = set(ids) - set(all_ids)
    if unknown:
        sys.exit(f"unknown task(s): {', '.join(sorted(unknown))}")
    return ids


def cmd_list(args) -> int:
    for tid in list_tasks(args.tasks_root):
        t = load_task(tid, args.tasks_root)
        print(f"{tid:20s} {t.difficulty:8s} {', '.join(t.tags)}")
    return 0


def cmd_score(args) -> int:
    task = load_task(args.task, args.tasks_root)
    code = Path(args.file).read_text()
    res = evaluate(task, code, use_cache=not args.no_cache)
    print(format_feedback(res, "full"))
    print(json.dumps({"score": res.score, "breakdown": res.breakdown,
                      "timings_s": res.timings_s}, indent=2))
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
                                                   use_cache=not args.no_cache), jobs))
    for (task, path), r in zip(jobs, results, strict=True):
        name = "ref.sv" if path == task.ref_path else path.name
        rows.append({"task": task.id, "candidate": name, "score": r.score,
                     "tests": f"{r.tests_passed}/{r.tests_total}",
                     "compile": r.compile_ok, "lint_warn": len(r.lint_warnings),
                     "cells": r.cells, "ref_cells": r.ref_cells, "depth": r.depth,
                     "violations": r.violations, "breakdown": r.breakdown})
    print(f"{'task':18s} {'candidate':30s} {'score':>6s} {'tests':>6s} {'cells':>6s} "
          f"{'ref':>5s} {'warn':>4s}  note")
    for row in rows:
        note = "; ".join(row["violations"])[:50] or ("" if row["compile"] else "compile error")
        print(f"{row['task']:18s} {row['candidate']:30s} {row['score']:6.3f} {row['tests']:>6s} "
              f"{str(row['cells']):>6s} {str(row['ref_cells']):>5s} {row['lint_warn']:4d}  {note}")
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
    while True:
        action = agent.act(obs)
        obs, reward, terminated, truncated, info = env.step(action)
        r = info["eval"]
        ret += reward
        turns.append({"turn": info["turn"], "score": r.score, "reward": round(reward, 4),
                      "tests": f"{r.tests_passed}/{r.tests_total}", "cells": r.cells,
                      "breakdown": r.breakdown, "timings_s": r.timings_s, "cached": r.cached})
        if terminated or truncated:
            break
    first = env.state.history[0]
    last = env.state.history[-1]
    return {
        "task": task_id,
        "turns": len(turns),
        "pass@1": first.tests_total > 0 and first.tests_passed == first.tests_total,
        "solved": last.tests_total > 0 and last.tests_passed == last.tests_total,
        "first_score": first.score,
        "best_score": env.state.best_score,
        "return": round(ret, 4),
        "wall_s": round(time.monotonic() - t0, 2),
        "trajectory": turns,
        "usage": getattr(agent, "usage", None),
    }


def cmd_run(args) -> int:
    env_kwargs = dict(tasks_root=args.tasks_root, max_turns=args.max_turns,
                      reward_mode=args.reward_mode, feedback=args.feedback,
                      use_cache=not args.no_cache)
    agent_kwargs: dict = {}
    if args.agent == "replay":
        agent_kwargs["tasks_root"] = args.tasks_root
    elif args.model:
        agent_kwargs["model"] = args.model
    ids = _tasks_arg(args.tasks, args.tasks_root)
    episodes = [tid for tid in ids for _ in range(args.samples)]
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda tid: run_episode(env_kwargs, args.agent, agent_kwargs,
                                                        tid), episodes))
    print(f"{'task':18s} {'turns':>5s} {'pass@1':>6s} {'solved':>6s} {'first':>6s} {'best':>6s}"
          f"  per-turn scores")
    for r in results:
        scores = " -> ".join(f"{t['score']:.2f}" for t in r["trajectory"])
        print(f"{r['task']:18s} {r['turns']:5d} {str(r['pass@1']):>6s} {str(r['solved']):>6s} "
              f"{r['first_score']:6.3f} {r['best_score']:6.3f}  {scores}")
    n = len(results)
    summary = {
        "agent": args.agent,
        "model": args.model,
        "episodes": n,
        "pass@1": sum(r["pass@1"] for r in results) / n,
        "solved_within_turns": sum(r["solved"] for r in results) / n,
        "mean_first_score": sum(r["first_score"] for r in results) / n,
        "mean_best_score": sum(r["best_score"] for r in results) / n,
        "mean_turns": sum(r["turns"] for r in results) / n,
        "wall_s": round(time.monotonic() - t0, 2),
        "tools": tool_versions(),
    }
    print("\n" + json.dumps({k: (round(v, 3) if isinstance(v, float) else v)
                             for k, v in summary.items()}, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "episodes": results}, indent=2,
                                             default=str))
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
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("baselines", help="grade the reference and all hand-written candidates")
    p.add_argument("--tasks", default="all")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out")
    p.add_argument("--no-cache", action="store_true")
    p.set_defaults(fn=cmd_baselines)

    p = sub.add_parser("run", help="run multi-turn episodes with an agent")
    p.add_argument("--agent", choices=["replay", "claude"], default="replay")
    p.add_argument("--model", help="Claude model id (default: $RTLGYM_MODEL or claude-sonnet-5-5)")
    p.add_argument("--tasks", default="all")
    p.add_argument("--samples", type=int, default=1, help="episodes per task")
    p.add_argument("--max-turns", type=int, default=3)
    p.add_argument("--reward-mode", choices=["improvement", "score"], default="improvement")
    p.add_argument("--feedback", choices=["none", "summary", "full"], default="full")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out")
    p.add_argument("--no-cache", action="store_true")
    p.set_defaults(fn=cmd_run)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
