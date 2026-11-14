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


def _turn_record(r, reward: float, info: dict) -> dict:
    return {"turn": info["turn"], "score": r.score, "reward": round(reward, 4),
            "tests": f"{r.tests_passed}/{r.tests_total}",
            "all_tests_pass": r.all_tests_pass, "formal": r.formal_status,
            "test_escape": r.test_escape, "inconclusive": r.inconclusive,
            "solved": info["solved"],
            "cells": r.cells, "breakdown": r.breakdown,
            "timings_s": r.timings_s, "grade_s": info["grade_s"],
            "cached": r.cached}


def _play(env: RTLEnv, agent, obs: dict, turns: list, ret: float,
          first_action: str | None = None) -> tuple[float, str | None]:
    """Run turns until the episode ends. Returns (return, error)."""
    try:
        while True:
            action = first_action if first_action is not None else agent.act(obs)
            first_action = None
            obs, reward, terminated, truncated, info = env.step(action)
            ret += reward
            turns.append(_turn_record(info["eval"], reward, info))
            if terminated or truncated:
                return ret, None
    except Exception as exc:  # noqa: BLE001 - one failed API call must not sink the run
        return ret, f"{type(exc).__name__}: {exc}"[:500]


def _episode_record(task_id: str, env: RTLEnv, turns: list, ret: float, error: str | None,
                    t0: float, usage) -> dict:
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
    t0 = time.monotonic()
    agent = make_agent(agent_name, **agent_kwargs)
    envs = {arm: RTLEnv(**{**env_kwargs, "feedback": arm}) for arm in arms}
    obs = {arm: env.reset(task_id=task_id)[0] for arm, env in envs.items()}
    agent.begin_episode(obs[arms[0]])
    try:
        first_action, error = agent.act(obs[arms[0]]), None
    except Exception as exc:  # noqa: BLE001
        first_action, error = None, f"{type(exc).__name__}: {exc}"[:500]
    shared = {"usage": dict(getattr(agent, "usage", None) or {}),
              "act_s": round(time.monotonic() - t0, 2), "error": error}
    # Fork every arm now, from the state right after the first attempt.
    branches = {arm: agent.fork() for arm in arms}
    out = {}
    for arm in arms:
        ta = time.monotonic()
        turns: list = []
        ret, err = (0.0, error) if first_action is None else \
            _play(envs[arm], branches[arm], obs[arm], turns, 0.0, first_action=first_action)
        rec = _episode_record(task_id, envs[arm], turns, ret, err, ta,
                              getattr(branches[arm], "usage", None))
        rec["shared_first"] = shared
        out[arm] = rec
    return out


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
        for k, v in (r.get("usage") or {}).items():
            usage[k] = round(usage.get(k, 0) + v, 2)
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
    return {
        **meta,
        "episodes": n,
        "errors": n - len(ok),
        "pass@1": frac("pass@1"),
        "pass@1_count": count("pass@1"),
        "pass@1_tests_only": frac("pass@1_tests_only"),
        "solved_within_turns": frac("solved"),
        "solved_count": count("solved"),
        "test_escape_attempts": sum(r["test_escapes"] for r in results),
        "inconclusive_attempts": sum(r.get("inconclusive", 0) for r in results),
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


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar test: a binomial test of b successes out of b + c
    discordant pairs, with p = 1/2. Returns 1.0 when there are no discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired_table(per_arm: dict[str, list[dict]], arms: tuple[str, str]) -> dict:
    """Per-task outcomes of paired episodes (same first attempt in both arms).

    An episode whose shared first attempt failed (e.g., an API error) has no
    outcome in either arm: it is counted as "errored" and left out of the other
    counts and the test. An episode whose first attempt was accepted cannot differ
    between the arms, so only the "informative" ones (first attempt not accepted)
    can become discordant pairs."""
    a, b = arms
    totals = {"both": 0, f"only_{a}": 0, f"only_{b}": 0, "neither": 0, "errored": 0}
    rows, informative = [], 0
    for ra, rb in zip(per_arm[a], per_arm[b], strict=True):
        if (ra.get("shared_first") or {}).get("error"):
            key = "errored"
        else:
            key = ("both" if ra["solved"] and rb["solved"] else f"only_{a}" if ra["solved"]
                   else f"only_{b}" if rb["solved"] else "neither")
            informative += not ra["pass@1"]
        totals[key] += 1
        rows.append({"task": ra["task"], "first_attempt_solved": ra["pass@1"],
                     f"{a}_solved": ra["solved"], f"{b}_solved": rb["solved"],
                     f"{a}_best": ra["best_score"], f"{b}_best": rb["best_score"],
                     f"{a}_error": ra["error"], f"{b}_error": rb["error"],
                     "outcome": key})
    shared: dict[str, float] = {"act_s": 0.0}
    for r in per_arm[a]:
        first = r.get("shared_first") or {}
        shared["act_s"] = round(shared["act_s"] + first.get("act_s", 0.0), 2)
        for k, v in (first.get("usage") or {}).items():
            shared[k] = round(shared.get(k, 0) + v, 2)
    only_a, only_b = totals[f"only_{a}"], totals[f"only_{b}"]
    return {"arms": list(arms), "episodes": len(rows), "outcomes": totals,
            "informative_episodes": informative, "discordant_pairs": only_a + only_b,
            "mcnemar_exact_p": round(mcnemar_exact(only_a, only_b), 4),
            "shared_first": shared, "rows": rows}


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
                                 if k not in ("per_task", "tasks")}, indent=2))
    if args.paired:
        paired = paired_table(per_arm, arms)
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
        scores = " -> ".join(f"{t['score']:.2f}" for t in r["trajectory"])
        if r["error"]:
            print(f"{r['task']:18s} ERROR {r['error'][:90]}" + (f"  (after {scores})"
                                                                 if scores else ""))
            continue
        print(f"{r['task']:18s} {r['turns']:5d} {str(r['pass@1']):>6s} {str(r['solved']):>6s} "
              f"{r['first_score']:6.3f} {r['best_score']:6.3f}  {scores}")


def _print_paired(p: dict) -> None:
    a, b = p["arms"]
    o = p["outcomes"]
    print(f"\nPaired outcomes over {p['episodes']} episodes (same first attempt in both arms):")
    print(f"  solved in both: {o['both']}   only with {a}: {o[f'only_{a}']}   "
          f"only with {b}: {o[f'only_{b}']}   in neither: {o['neither']}   "
          f"errored before a first attempt: {o['errored']}")
    print(f"  {p['informative_episodes']} informative episode(s) (first attempt not accepted); "
          f"{p['discordant_pairs']} discordant pair(s), exact McNemar p = "
          f"{p['mcnemar_exact_p']}.")


def _pct(v) -> str:
    return "n/a" if v is None else f"{100 * v:.0f}%"


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


def cmd_report(args) -> int:
    """Turn one or more `run --out` files into Markdown tables."""
    data = [json.loads(Path(f).read_text()) for f in args.files]
    runs = [d["summary"] for d in data if "summary" in d]      # skip paired summaries
    print("| Arm | Episodes (errors) | Accepted on 1st attempt | 1st attempt passes tests "
          "| Accepted within N turns | Test escapes | Inconclusive | Mean turns "
          "| Grading p50 / p95 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in runs:
        n = s["episodes"]
        print(f"| {_arm(s)} | {n} ({s['errors']}) | "
              f"{_count(s['pass@1'], n)} | {_count(s['pass@1_tests_only'], n)} | "
              f"{_count(s['solved_within_turns'], n)} (N={s['max_turns']}) | "
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
            cells.append("n/a" if not pt else
                         f"{_count(pt['pass@1'], pt['episodes'])} → "
                         f"{_count(pt['solved'], pt['episodes'])}")
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
    p.add_argument("--agent", choices=["replay", "claude", "ollama"], default="replay")
    p.add_argument("--model", help="Claude model ID (default: $RTLGYM_MODEL or claude-sonnet-5-5); "
                                    "with --agent ollama, a local model name such as qwen3:14b")
    p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                   help="Claude effort level (default: the model's own default)")
    p.add_argument("--max-tokens", type=_positive_int,
                   help="output token limit per call, thinking included "
                        "(default: the model's own for Claude; 8192 for --agent ollama)")
    p.add_argument("--tasks", default="all")
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
