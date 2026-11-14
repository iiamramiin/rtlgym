"""Summaries for local-model runs.

  python make_table.py table DIR      Markdown tables for every result file in DIR
  python make_table.py estimate DIR TASKS ARMS SAMPLES TURNS
                                      run-time estimate from the probe files in DIR

"Mean best score" is the mean, over episodes, of the best score reached. (In the
default "improvement" reward mode this equals the episode return; in "score" mode
the return also depends on how many turns were used, so it is not shown.)
Result files from the Claude eval workflow can be put in DIR to compare.
"""

import json
import sys
from pathlib import Path


def load(path: Path):
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return None
    return data if "summary" in data or "paired" in data else None


def count(rate, n):
    return "n/a" if rate is None else f"{round(rate * n)}/{n}"


def table(folder: str) -> None:
    head = ("Model", "Feedback", "Episodes (errors)", "Solved on 1st try",
            "Solved within N turns", "Mean best score", "Mean 1st-attempt score",
            "Test escapes", "Time per reply", "N (turns)", "Settings")
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    paired = []
    for p in sorted(Path(folder).glob("*.json")):
        d = load(p)
        if not d:
            continue
        if "paired" in d:
            paired.append((d["meta"].get("model"), d["paired"]))
            continue
        s, n = d["summary"], d["summary"]["episodes"]
        usage = s.get("usage") or {}
        calls = usage.get("calls") or 0
        o = s.get("ollama") or {}
        settings = []
        if o:
            think = o.get("think_requested", o.get("think"))
            settings.append("think " + {None: "default", True: "on", False: "off"}.get(think,
                                                                                    str(think)))
            q = (o.get("build") or {}).get("quantization")
            if q:
                settings.append(q)
        if s.get("paired"):
            settings.append("paired")
        print("| " + " | ".join((
            str(s.get("model") or s.get("agent")), str(s.get("feedback")),
            f"{n} ({s['errors']})", count(s["pass@1"], n),
            count(s["solved_within_turns"], n),
            "n/a" if s["mean_best_score"] is None else f"{s['mean_best_score']:.3f}",
            "n/a" if s["mean_first_score"] is None else f"{s['mean_first_score']:.3f}",
            str(s["test_escape_attempts"]),
            f"{usage['generate_s'] / calls:.0f} s" if calls and "generate_s" in usage else "n/a",
            str(s["max_turns"]), ", ".join(settings) or "-")) + " |")
    for model, t in paired:
        a, b = t["arms"]
        o = t["outcomes"]
        print(f"\nPaired outcomes, {model} ({t['episodes']} episodes, same first attempt in "
              f"both arms): solved in both {o['both']}, only with {a} {o[f'only_{a}']}, "
              f"only with {b} {o[f'only_{b}']}, in neither {o['neither']}. "
              f"Only the {t['discordant_pairs']} discordant pair(s) inform the comparison.")


def estimate(folder: str, tasks: int, arms: int, samples: int, turns: int) -> None:
    print("\nEstimated time for the full run (from the probe; rough):")
    total = 0.0
    for p in sorted(Path(folder).glob("*.json")):
        d = load(p)
        if not d or "summary" not in d:
            continue
        s, eps = d["summary"], d["episodes"]
        usage = s.get("usage") or {}
        calls = usage.get("calls") or 0
        if not calls:
            print(f"  {s.get('model')}: probe failed ({eps[0]['error'] if eps else 'no episodes'})")
            continue
        per_call = usage["generate_s"] / calls
        grade = s["wall_s"] / max(1, sum(e["turns"] for e in eps)) - per_call
        # Assume about 2 of the allowed turns are used per episode on average.
        n_calls = tasks * arms * samples * min(turns, 2)
        sec = n_calls * (per_call + max(0.0, grade))
        total += sec
        print(f"  {s.get('model'):18s} {per_call:6.0f} s per reply -> about {sec / 3600:.1f} h "
              f"({n_calls} replies)")
    print(f"  all models: about {total / 3600:.1f} h")


if __name__ == "__main__":
    if sys.argv[1] == "table":
        table(sys.argv[2])
    else:
        estimate(sys.argv[2], *(int(x) for x in sys.argv[3:7]))
