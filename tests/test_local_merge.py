# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Merge completed disjoint paired blocks without mixing experiments or raw bytes."""

import hashlib
import json
import runpy
from pathlib import Path

import pytest

from rtlgym import cli
from rtlgym.stats import clopper_pearson

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/local/merge_runs.py"
MERGE = runpy.run_path(str(SCRIPT))
MODEL = "qwen3:14b"


def _episode(task, solved):
    shared = {"usage": {"calls": 1, "input_tokens": 10, "output_tokens": 10,
                        "generate_s": 1.5, "eval_s": 1.2, "truncated": 0},
              "act_s": 1.5, "error": None}
    turns = [{"turn": i + 1, "score": float(solved and i == 2), "grade_s": 0.1,
              "cached": False, "code": "module dut; endmodule", "test_escape": False,
              "usage": shared["usage"] if i == 0 else {"calls": 1, "truncated": 0}}
             for i in range(3)]
    return {"task": task, "task_kind": "design", "error": None, "turns": 3,
            "pass@1": False, "pass@1_tests_only": False, "solved": solved,
            "first_score": 0.0, "best_score": float(solved), "return": float(solved),
            "test_escapes": 0, "inconclusive": 0, "trajectory": turns, "wall_s": 4.0,
            "shared_first": shared, "usage": {"calls": 2, "generate_s": 4.0, "eval_s": 3.0,
                                               "input_tokens": 20, "output_tokens": 20, "truncated": 0}}


def _part(folder, tasks, seed, *, model=MODEL, samples=1):
    folder.mkdir(parents=True, exist_ok=True)
    order = [task for task in tasks for _ in range(samples)]
    rows = {arm: [_episode(task, arm == "full") for task in order] for arm in ("full", "none")}
    meta = {"agent": "ollama", "model": model, "effort": None, "samples_per_task": samples,
            "max_turns": 3, "feedback": "full", "reward_mode": "improvement", "formal": True,
            "formal_by_task": dict.fromkeys(tasks, True), "tasks": tasks,
            "started_utc": "2026-11-22T12:00:00+00:00", "wall_s": 12.0 * len(order),
            "git_commit": "a" * 40, "python": "3.12.3",
            "tools": {"cocotb": "2.1.0", "iverilog": "12.0", "verilator": "5.020",
                      "yosys": "0.33", "sv2v": "v0.0.13"},
            "seed": {"base": seed, "per_episode": "base + episode index"},
            "ollama": {"host": "http://localhost:11434", "options": {"seed": seed,
                        "num_ctx": 8192, "num_predict": 8192}, "think": False, "think_requested": False,
                       "think_ignored": False, "timeout_s": 1800.0,
                       "build": {"model": model, "digest": "b" * 64, "quantization": "Q4_K_M",
                                 "ollama_version": "0.40.16"}}}
    slug = model.replace(":", "_").replace("/", "_")
    for arm in ("full", "none"):
        summary = cli.summarize(rows[arm], {**meta, "feedback": arm, "paired": True,
                                            "pair_arms": ["full", "none"]})
        summary.update(arm_s=4.0 * len(order), shared_first_s=1.5 * len(order))
        (folder / f"{slug}__{arm}.json").write_text(json.dumps({"summary": summary, "episodes": rows[arm]}))
    (folder / f"{slug}__paired.json").write_text(json.dumps({
        "meta": meta, "paired": cli.paired_table(rows, ("full", "none"), meta["formal_by_task"]),
    }))
    return folder


def _read(path):
    return json.loads(path.read_text())


def _edit_meta(folder, change, *, all_files=True):
    paths = sorted(folder.glob("qwen3_14b__*.json")) if all_files else [folder / "qwen3_14b__full.json"]
    for path in paths:
        data = _read(path)
        change(data.get("meta", data.get("summary")))
        path.write_text(json.dumps(data))


def test_merge_rebuilds_counts_intervals_pairs_and_call_usage_without_writing_raws(tmp_path):
    a = _part(tmp_path / "a", ["task_a"], 20261122)
    b = _part(tmp_path / "b", ["task_b"], 20261123)
    before = {path: path.read_bytes() for folder in (a, b) for path in folder.glob("*.json")}
    out = tmp_path / "merged"
    paths = MERGE["merge_runs"](MODEL, out, [a, b])
    assert len(paths) == 3 and {path.name for path in paths} == {
        f"qwen3_14b__{arm}.json" for arm in ("full", "none", "paired")}
    full, none, pair = (_read(out / f"qwen3_14b__{arm}.json") for arm in ("full", "none", "paired"))
    sf, sn, paired, meta = full["summary"], none["summary"], pair["paired"], pair["meta"]
    assert sf["episodes"] == sn["episodes"] == paired["episodes"] == 2
    assert sf["solved_count"] == "2/2" and sn["solved_count"] == "0/2"
    assert sf["pass@1_count"] == sn["pass@1_count"] == "0/2"
    assert sf["pass@1_ci95"] == list(clopper_pearson(0, 2))
    assert sf["solved_within_turns_ci95"] == list(clopper_pearson(2, 2))
    assert sn["solved_within_turns_ci95"] == list(clopper_pearson(0, 2))
    assert paired["outcomes"]["only_full"] == 2 and paired["mcnemar_exact_p"] == 0.5
    assert sf["usage"]["calls"] + sn["usage"]["calls"] + paired["shared_first"]["calls"] == 10
    assert sf["wall_s"] == sn["wall_s"] == meta["wall_s"] == 24
    assert sf["arm_s"] == sn["arm_s"] == 8 and sf["shared_first_s"] == sn["shared_first_s"] == 3
    assert paired["shared_first"]["act_s"] == 3
    assert meta["tasks"] == ["task_a", "task_b"] and meta["git_commit"] == "a" * 40
    assert meta["seed"]["base"] == meta["ollama"]["options"]["seed"] == 20261122
    assert meta["merge"]["parts"][1]["episode_offset"] == 1
    assert meta["merge"]["parts"][1]["seed_base"] == 20261123
    assert str(tmp_path) not in json.dumps(meta["merge"])
    for part in meta["merge"]["parts"]:
        for record in part["files"]:
            original = (a, b)[part["part"] - 1] / record["name"]
            assert hashlib.sha256(original.read_bytes()).hexdigest() == record["sha256"]
    assert all(len(value) == 64 for value in meta["merge"]["reporting_sources"].values())
    assert {path: path.read_bytes() for path in before} == before


def test_other_models_are_ignored_instead_of_pooled(tmp_path):
    a = _part(tmp_path / "a", ["task_a"], 100)
    b = _part(tmp_path / "b", ["task_b"], 101)
    _part(a, ["other_a"], 500, model="llama3.1:8b")
    _part(b, ["other_b"], 501, model="llama3.1:8b")
    out = tmp_path / "out"
    MERGE["merge_runs"](MODEL, out, [a, b])
    assert _read(out / "qwen3_14b__full.json")["summary"]["tasks"] == ["task_a", "task_b"]
    assert len(list(out.glob("*.json"))) == 3


@pytest.mark.parametrize("missing", ["tool", "python", "digest", "quantization", "version"])
def test_matching_placeholder_versions_are_still_insufficient(tmp_path, missing):
    a = _part(tmp_path / "a", ["task_a"], 100)
    b = _part(tmp_path / "b", ["task_b"], 101)

    def change(meta):
        if missing == "tool":
            meta["tools"]["yosys"] = "missing"
        elif missing == "python":
            meta["python"] = "unknown"
        else:
            meta["ollama"]["build"]["ollama_version" if missing == "version" else missing] = "unknown"

    for part in (a, b):
        _edit_meta(part, change)
    with pytest.raises(ValueError):
        MERGE["merge_runs"](MODEL, tmp_path / "out", [a, b])
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("setting", [
    "git_commit", "python", "tool", "digest", "quantization", "version", "context", "output",
    "reasoning", "reward", "formal", "samples", "turns",
])
def test_changed_generation_settings_are_rejected_before_creating_output(tmp_path, setting):
    a = _part(tmp_path / "a", ["task_a"], 100)
    b = _part(tmp_path / "b", ["task_b"], 101)

    def change(meta):
        if setting in ("git_commit", "python"):
            meta[setting] = "c" * 40 if setting == "git_commit" else "3.13.0"
        elif setting == "tool":
            meta["tools"]["sv2v"] = "different"
        elif setting in ("digest", "quantization", "version"):
            meta["ollama"]["build"]["ollama_version" if setting == "version" else setting] = "different"
        elif setting in ("context", "output"):
            meta["ollama"]["options"]["num_ctx" if setting == "context" else "num_predict"] = 4096
        elif setting == "reasoning":
            meta["ollama"]["think"] = meta["ollama"]["think_requested"] = True
        elif setting == "reward":
            meta["reward_mode"] = "score"
        elif setting == "formal":
            meta["formal"] = False
        else:
            meta["samples_per_task" if setting == "samples" else "max_turns"] += 1

    _edit_meta(b, change)
    with pytest.raises(ValueError):
        MERGE["merge_runs"](MODEL, tmp_path / "out", [a, b])
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("problem", ["noncontiguous", "policy", "options", "within_pair"])
def test_seed_metadata_must_be_recorded_contiguous_and_consistent(tmp_path, problem):
    a = _part(tmp_path / "a", ["task_a"], 100)
    b = _part(tmp_path / "b", ["task_b"], 102 if problem == "noncontiguous" else 101)
    if problem == "policy":
        _edit_meta(b, lambda meta: meta["seed"].update(per_episode="fixed"))
    elif problem == "options":
        _edit_meta(b, lambda meta: meta["ollama"]["options"].update(seed=999))
    elif problem == "within_pair":
        _edit_meta(b, lambda meta: meta["seed"].update(base=999), all_files=False)
    with pytest.raises(ValueError):
        MERGE["merge_runs"](MODEL, tmp_path / "out", [a, b])
    assert not (tmp_path / "out").exists()


def test_seed_offsets_count_episodes_not_tasks_or_arms(tmp_path):
    a = _part(tmp_path / "a", ["task_a"], 100, samples=2)
    b = _part(tmp_path / "b", ["task_b"], 102, samples=2)
    out = tmp_path / "out"
    MERGE["merge_runs"](MODEL, out, [a, b])
    assert _read(out / "qwen3_14b__full.json")["summary"]["episodes"] == 4


@pytest.mark.parametrize("problem", ["overlap", "order", "missing", "duplicate", "paired", "unfinished"])
def test_incomplete_or_overlapping_blocks_are_rejected(tmp_path, problem):
    a = _part(tmp_path / "a", ["task_a"], 100)
    b = _part(tmp_path / "b", ["task_a"] if problem == "overlap" else ["task_b", "task_c"], 101)
    path = b / "qwen3_14b__none.json"
    if problem == "order":
        data = _read(path)
        data["episodes"].reverse()
        path.write_text(json.dumps(data))
    elif problem == "missing":
        path.unlink()
    elif problem == "duplicate":
        (b / "duplicate.json").write_bytes(path.read_bytes())
    elif problem == "paired":
        path = b / "qwen3_14b__paired.json"
        data = _read(path)
        data["paired"]["outcomes"]["only_full"] = 999
        path.write_text(json.dumps(data))
    elif problem == "unfinished":
        data = _read(path)
        data["episodes"][0]["turns"] = 2
        data["episodes"][0]["trajectory"].pop()
        path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        MERGE["merge_runs"](MODEL, tmp_path / "out", [a, b])
    assert not (tmp_path / "out").exists()


def test_existing_outputs_and_input_directories_are_not_overwritten(tmp_path):
    a = _part(tmp_path / "a", ["task_a"], 100)
    b = _part(tmp_path / "b", ["task_b"], 101)
    out = tmp_path / "out"
    out.mkdir()
    sentinel = out / "qwen3_14b__full.json"
    sentinel.write_bytes(b"keep these bytes")
    for target in (out, a, a / "nested"):
        with pytest.raises(ValueError, match="new directory"):
            MERGE["merge_runs"](MODEL, target, [a, b])
    assert sentinel.read_bytes() == b"keep these bytes"


def test_merge_command_and_clean_generation_commit_guard(tmp_path):
    a = _part(tmp_path / "a", ["task_a"], 100)
    b = _part(tmp_path / "b", ["task_b"], 101)
    assert MERGE["main"](["--model", MODEL, "--out", str(tmp_path / "out"), str(a), str(b)]) == 0
    _edit_meta(a, lambda meta: meta.update(git_commit="a" * 40 + "-dirty"))
    with pytest.raises(SystemExit) as error:
        MERGE["main"](["--model", MODEL, "--out", str(tmp_path / "other"), str(a), str(b)])
    assert error.value.code == 2
