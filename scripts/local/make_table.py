# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Local-model result tables and conservative paired call-count estimates."""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rtlgym.cli import mcnemar_exact, refresh_report  # noqa: E402
from rtlgym.stats import clopper_pearson, format_ci  # noqa: E402


def load(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if "summary" in data:
        return refresh_report(data) if data.get("episodes") else data
    return data if "paired" in data else None


def _exact_count(summary: dict, key: str) -> tuple[int, int] | None:
    count_key = "pass@1_count" if key == "pass@1" else "solved_count"
    try:
        numerator, denominator = map(int, summary[count_key].split("/"))
    except (KeyError, TypeError, ValueError):
        return None
    if denominator != summary["episodes"] or not 0 <= numerator <= denominator:
        return None
    return numerator, denominator


def _rate(summary: dict, key: str) -> str:
    counts = _exact_count(summary, key)
    if counts is None:
        return "n/a"
    return f"{counts[0]}/{counts[1]} {format_ci(clopper_pearson(*counts))}"


def _settings(summary: dict) -> str:
    ollama = summary.get("ollama") or {}
    options = ollama.get("options") or {}
    settings = []
    if ollama:
        think = ollama.get("think_requested", ollama.get("think"))
        actual = ollama.get("think")
        label = {None: "default", True: "on", False: "off"}.get(think, str(think))
        if think is not None and actual is None:
            label += " (unsupported)"
        settings.append("think " + label)
        for key in ("num_ctx", "num_predict", "seed"):
            if key in options:
                settings.append(f"{key}={options[key]}")
        quantization = (ollama.get("build") or {}).get("quantization")
        if quantization:
            settings.append(quantization)
    if summary.get("paired"):
        settings.append("paired")
    return ", ".join(settings) or "-"


def _accumulate_usage(totals: dict, name: str, usage: dict) -> None:
    total = totals.setdefault(name, {"calls": 0, "generate_s": 0.0, "timed_calls": 0})
    calls = usage.get("calls", 0)
    total["calls"] += calls
    seconds = usage.get("generate_s")
    if calls and isinstance(seconds, (int, float)) and math.isfinite(seconds) and seconds >= 0:
        total["generate_s"] += seconds
        total["timed_calls"] += calls


def table(folder: str) -> None:
    head = ("Model", "Feedback", "Episodes (errors)", "First attempt (95% CI)",
            "Within N turns (95% CI)", "Mean best score", "Truncated", "Test escapes",
            "N (turns)", "Settings")
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    arms, paired = [], []
    for path in sorted(Path(folder).glob("*.json")):
        data = load(path)
        if not data:
            continue
        if "paired" in data:
            paired.append((data["meta"].get("model") or data["meta"].get("agent"), data["paired"]))
            continue
        summary = data["summary"]
        arms.append(summary)
        name = summary.get("model") or summary.get("agent")
        score = summary.get("mean_best_score")
        print("| " + " | ".join((
            str(name), str(summary.get("feedback")),
            f"{summary['episodes']} ({summary['errors']})",
            _rate(summary, "pass@1"), _rate(summary, "solved_within_turns"),
            "n/a" if score is None else f"{score:.3f}",
            str(summary.get("truncated_attempts", 0)),
            str(summary["test_escape_attempts"]), str(summary["max_turns"]),
            _settings(summary))) + " |")
    print("\nIntervals are exact 95% Clopper–Pearson binomial bounds, separately for each arm; "
          "errors remain in the denominator. These pooled-task intervals describe this "
          "sample and do not establish generalization to new task families.")

    if paired:
        print("\n| Model | Paired episodes | Both | Only full | Only none | Neither | Errored | "
              "Informative | Discordant | Exact McNemar p |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for model, group in paired:
            a, b = group["arms"]
            outcomes = group["outcomes"]
            only_a, only_b = outcomes[f"only_{a}"], outcomes[f"only_{b}"]
            # Recompute when reading historical files that rounded small p-values.
            p_value = mcnemar_exact(only_a, only_b)
            print(f"| {model} | {group['episodes']} | {outcomes['both']} | {only_a} | {only_b} | "
                  f"{outcomes['neither']} | {outcomes.get('errored', 0)} | "
                  f"{group.get('informative_episodes', 'n/a')} | {group['discordant_pairs']} | "
                  f"{p_value:.6g} |")
        print("\nMcNemar uses the discordant full/none pairs within each model. "
              "Shared first attempts are not independent observations.")

    tasks = sorted({task for summary in arms for task in summary.get("per_task", {})})
    if tasks:
        columns = [f"{summary.get('model') or summary.get('agent')} / {summary['feedback']}"
                   for summary in arms]
        print("\n| Task | " + " | ".join(columns) + " |")
        print("|---|" + "---:|" * len(arms))
        for task in tasks:
            cells = []
            for summary in arms:
                per_task = summary.get("per_task", {}).get(task)
                if per_task is None:
                    cells.append("n/a")
                    continue
                cell = f"{per_task['pass@1_count']} → {per_task['solved_count']}"
                if per_task.get("truncated_attempts"):
                    cell += f"; {per_task['truncated_attempts']} truncated"
                cells.append(cell)
            print(f"| {task} | " + " | ".join(cells) + " |")
        print("\nPer-task cells: accepted first → accepted within the turn budget.")

    # A paired first call appears in both trajectories, but is counted once here.
    totals = {}
    for summary in arms:
        name = summary.get("model") or summary.get("agent")
        _accumulate_usage(totals, name, summary.get("usage") or {})
    for name, group in paired:
        _accumulate_usage(totals, name, group.get("shared_first") or {})
    if totals:
        print("\n| Model | Unique calls | Mean seconds per reply |")
        print("|---|---:|---:|")
        for name, total in totals.items():
            calls = total["calls"]
            seconds = (f"{total['generate_s'] / calls:.2f}"
                       if calls and total["timed_calls"] == calls else "n/a")
            print(f"| {name} | {calls} | {seconds} |")


def call_budget(tasks: int, samples: int, turns: int, paired: bool, arms: int = 2) -> int:
    if min(tasks, samples, turns, arms) < 1:
        raise ValueError("tasks, samples, turns and arms must be positive")
    return tasks * samples * (1 + 2 * (turns - 1) if paired else arms * turns)


def estimate(folder: str, tasks: int, arms: int, samples: int, turns: int, paired: bool = False) -> None:
    print("\nEstimated run time from the probe (rough; larger designs can reply more slowly):")
    calls_max = call_budget(tasks, samples, turns, paired, arms)
    print(f"{tasks * samples} episodes per model; at most {calls_max} unique calls "
          f"({'paired' if paired else 'independent arms'}).")
    for path in sorted(Path(folder).glob("*.json")):
        data = load(path)
        if not data or "summary" not in data:
            continue
        summary, episodes = data["summary"], data["episodes"]
        usage = summary.get("usage") or {}
        calls = usage.get("calls") or 0
        if not calls:
            print(f"  {summary.get('model')}: probe failed "
                  f"({episodes[0]['error'] if episodes else 'no episodes'})")
            continue
        reply_s = usage["generate_s"] / calls
        grade_s = max(0.0, summary["wall_s"] / calls - reply_s)
        hours = calls_max * (reply_s + grade_s) / 3600
        print(f"  {summary.get('model')}: {reply_s:.2f} s per reply; "
              f"{grade_s:.2f} s overhead per call; {hours:.2f} h at the maximum call count")
    print("The call count is an upper bound. Probe latency is not an upper bound: "
          "longer replies, growing contexts, tool timeouts and memory pressure can add time.")


if __name__ == "__main__":
    if sys.argv[1] == "table":
        table(sys.argv[2])
    else:
        estimate(sys.argv[2], *(int(value) for value in sys.argv[3:7]),
                 paired=len(sys.argv) > 7 and sys.argv[7] == "1")
