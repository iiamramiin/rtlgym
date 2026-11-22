# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Offline merge of one model's disjoint, complete paired task blocks.

python scripts/local/merge_runs.py --model qwen3:14b --out NEWDIR BLOCK_A BLOCK_B

Parts are ordered: seed bases must advance by the preceding episode count. This
does not merge repeated tasks, resumptions, models, or different run settings.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ARMS = ("full", "none")
META_KEYS = ("agent", "model", "effort", "samples_per_task", "max_turns", "reward_mode",
             "formal", "git_commit", "python", "tools", "ollama")
TOOLS = ("cocotb", "iverilog", "verilator", "yosys", "sv2v")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _seconds(value, label: str) -> float:
    _require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
             f"{label} must be a nonnegative finite time")
    return value


def _recorded(value) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().lower() not in {
        "unknown", "missing", "not found", "unavailable", "n/a",
    }


def _signature(meta: dict, model: str) -> dict:
    _require(all(key in meta for key in META_KEYS), "incomplete generation metadata")
    _require(meta["agent"] == "ollama" and meta["model"] == model, "model or agent mismatch")
    commit = meta["git_commit"]
    _require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
             "a clean, recorded generation commit is required")
    _require(_recorded(meta["python"]) and type(meta["formal"]) is bool,
             "missing Python or formal settings")
    for key in ("samples_per_task", "max_turns"):
        _require(type(meta[key]) is int and meta[key] > 0, f"invalid {key}")
    versions = meta["tools"]
    _require(isinstance(versions, dict) and all(_recorded(versions.get(key)) for key in TOOLS),
             "all grading tool versions must be recorded")
    seed = meta.get("seed") or {}
    _require(type(seed.get("base")) is int and seed.get("per_episode") == "base + episode index",
             "recorded base + episode index seed policy is required")
    ollama = meta["ollama"]
    _require(isinstance(ollama, dict), "missing Ollama settings")
    options, build = ollama.get("options", {}), ollama.get("build", {})
    _require(isinstance(options, dict) and isinstance(build, dict), "invalid Ollama build or options")
    _require(all(type(options.get(key)) is int and options[key] > 0
                 for key in ("num_ctx", "num_predict")), "missing context or output limit")
    _require(options.get("seed") == seed["base"], "Ollama seed does not match the recorded seed base")
    _require(all(key in ollama for key in ("think", "think_requested", "think_ignored", "timeout_s", "host")),
             "incomplete reasoning or execution settings")
    digest = build.get("digest")
    _require(build.get("model") == model and isinstance(digest, str)
             and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
             and _recorded(build.get("quantization")) and _recorded(build.get("ollama_version")),
             "model digest, quantization and Ollama version are required")
    signature = {key: copy.deepcopy(meta[key]) for key in META_KEYS}
    del signature["ollama"]["options"]["seed"]
    return signature


def _load_part(folder: Path, model: str, cli) -> dict:
    _require(folder.is_dir(), "each part must be a directory")
    selected = {}
    for path in sorted(folder.glob("*.json")):
        raw = path.read_bytes()
        data = json.loads(raw)
        if not isinstance(data, dict):
            continue
        meta = data.get("meta") if "paired" in data else data.get("summary")
        if not isinstance(meta, dict) or meta.get("model") != model:
            continue
        key = "paired" if "paired" in data else meta.get("feedback")
        _require(key in (*ARMS, "paired") and key not in selected,
                 "each part needs exactly one full, none and paired file for the selected model")
        selected[key] = (path, data, hashlib.sha256(raw).hexdigest())
    _require(set(selected) == {*ARMS, "paired"}, "incomplete paired file set for the selected model")
    pair = selected["paired"][1]
    meta = pair["meta"]
    signature = _signature(meta, model)
    tasks = meta.get("tasks")
    _require(isinstance(tasks, list) and tasks and all(isinstance(task, str) for task in tasks)
             and len(tasks) == len(set(tasks)), "task IDs must be nonempty and unique within a part")
    formal = meta.get("formal_by_task")
    _require(isinstance(formal, dict) and set(formal) == set(tasks)
             and all(type(value) is bool for value in formal.values()), "incomplete per-task formal settings")
    count = len(tasks) * meta["samples_per_task"]
    order = [task for task in tasks for _ in range(meta["samples_per_task"])]
    wall = _seconds(meta.get("wall_s"), "run wall_s")
    _require(isinstance(meta.get("started_utc"), str) and meta["started_utc"], "missing start time")
    rows = {}
    for arm in ARMS:
        data = selected[arm][1]
        summary, episodes = data["summary"], data.get("episodes")
        _require(_signature(summary, model) == signature, "generation settings differ within a paired part")
        _require(summary.get("paired") is True and summary.get("pair_arms") == list(ARMS),
                 "only full/none paired runs can be merged")
        for key in ("tasks", "formal_by_task", "seed", "started_utc", "wall_s"):
            _require(summary.get(key) == meta.get(key), f"paired metadata disagree on {key}")
        _require(isinstance(episodes, list) and len(episodes) == count
                 and summary.get("episodes") == count, "incomplete episode set")
        _require([row.get("task") for row in episodes] == order, "paired episode task orders differ")
        for row in episodes:
            turns = row.get("turns")
            _require(type(turns) is int and 0 <= turns <= meta["max_turns"]
                     and turns == len(row.get("trajectory", [])), "incomplete turn records")
            _require(row.get("error") or row.get("solved") or turns == meta["max_turns"],
                     "an unfinished episode cannot be merged")
        rows[arm] = episodes
        arm_s = round(sum(_seconds(row.get("wall_s"), "arm wall_s") for row in episodes), 2)
        _require(summary.get("arm_s") == arm_s, "arm timing does not match episodes")
        _require(summary.get("shared_first_s") == round(sum(
            _seconds(row.get("shared_first", {}).get("act_s"), "shared first act_s")
            for row in episodes), 2), "shared timing does not match episodes")
    for full, none in zip(rows["full"], rows["none"], strict=True):
        _require(full.get("shared_first") == none.get("shared_first"), "shared first calls disagree")
        for key in ("task_kind", "pass@1", "first_score"):
            _require(full.get(key) == none.get(key), "paired first-attempt grades disagree")
        first_full, first_none = full.get("trajectory", [])[:1], none.get("trajectory", [])[:1]
        _require(bool(first_full) == bool(first_none), "paired first attempts are incomplete")
        if first_full:
            _require(first_full[0].get("code") == first_none[0].get("code"), "paired first sources disagree")
    rebuilt = cli.paired_table(rows, ARMS, formal)
    recorded = pair["paired"]
    _require(recorded.get("arms") == list(ARMS), "paired arms must be full and none")
    for key in ("episodes", "rows", "outcomes", "informative_episodes", "discordant_pairs", "shared_first"):
        _require(recorded.get(key) == rebuilt[key], f"paired record disagrees with episodes: {key}")
    return {"meta": meta, "signature": signature, "rows": rows, "selected": selected, "wall_s": wall}


def merge_runs(model: str, out: Path, folders: list[Path]) -> list[Path]:
    """Validate all inputs, then write three new derived JSON files without model calls."""
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)
    from rtlgym import cli, stats

    _require(len(folders) >= 2, "at least two disjoint task blocks are required")
    out = out.resolve()
    resolved = [folder.resolve() for folder in folders]
    _require(not out.exists() and not any(out.is_relative_to(folder) for folder in resolved),
             "output must be a new directory outside all input parts")
    parts = [_load_part(folder, model, cli) for folder in resolved]
    first = parts[0]
    meta = copy.deepcopy(first["meta"])
    tasks, formal, provenance = [], {}, []
    rows = {arm: [] for arm in ARMS}
    expected_seed = meta["seed"]["base"]
    for index, part in enumerate(parts, 1):
        current = part["meta"]
        _require(part["signature"] == first["signature"], "generation settings differ between parts")
        _require(not set(tasks).intersection(current["tasks"]), "task IDs overlap between parts")
        _require(current["seed"]["base"] == expected_seed, "seed bases must be contiguous in part order")
        count = len(part["rows"]["full"])
        provenance.append({
            "part": index, "tasks": current["tasks"], "episode_offset": len(rows["full"]),
            "episodes": count, "seed_base": expected_seed, "started_utc": current["started_utc"],
            "wall_s": part["wall_s"],
            "files": [{"name": path.name, "sha256": digest}
                      for path, _, digest in part["selected"].values()],
        })
        expected_seed += count
        tasks.extend(current["tasks"])
        formal.update(current["formal_by_task"])
        for arm in ARMS:
            rows[arm].extend(copy.deepcopy(part["rows"][arm]))
    meta.update(tasks=tasks, formal_by_task=formal, wall_s=round(sum(part["wall_s"] for part in parts), 2))
    meta["merge"] = {
        "kind": "disjoint task blocks", "parts": provenance,
        "wall_time_basis": "sum of recorded part runs, excluding gaps",
        "reporting_sources": {name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                              for name, path in (("merge_runs.py", __file__), ("rtlgym/cli.py", cli.__file__),
                                                 ("rtlgym/stats.py", stats.__file__))},
    }
    datasets = {}
    for arm in ARMS:
        summary = cli.summarize(rows[arm], {**meta, "feedback": arm, "paired": True, "pair_arms": list(ARMS)})
        summary["arm_s"] = round(sum(row["wall_s"] for row in rows[arm]), 2)
        summary["shared_first_s"] = round(sum(row["shared_first"]["act_s"] for row in rows[arm]), 2)
        datasets[arm] = {"summary": summary, "episodes": rows[arm]}
    datasets["paired"] = {"meta": meta, "paired": cli.paired_table(rows, ARMS, formal)}
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", model)
    encoded = {out / f"{slug}__{arm}.json": json.dumps(data, indent=2, allow_nan=False) + "\n"
               for arm, data in datasets.items()}
    out.mkdir(parents=True, exist_ok=False)
    for path, text in encoded.items():
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return list(encoded)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("parts", nargs="+", type=Path)
    args = parser.parse_args(argv)
    try:
        paths = merge_runs(args.model, args.out, args.parts)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(str(exc))
    print(f"Merged {len(args.parts)} task blocks for {args.model}; wrote {len(paths)} derived files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
