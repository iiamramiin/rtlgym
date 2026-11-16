# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Separate outcomes for tasks with and without formal verification."""

import importlib.util
import json
from pathlib import Path

import pytest

from rtlgym import cli


def episode(task, *, first=False, solved=False, error=None):
    return {
        "task": task, "turns": 0, "error": error, "pass@1": first, "pass@1_tests_only": first,
        "solved": solved, "test_escapes": 0, "first_score": 0, "best_score": 0, "trajectory": [],
        "wall_s": 0, "usage": {},
    }


def test_mixed_acceptance_summary_keeps_every_episode():
    results = [
        episode("popcount16", first=True, solved=True),
        episode("popcount16", solved=True),
        episode("async_fifo", first=True, solved=True),
        episode("async_fifo", error="failed before grading"),
    ]
    summary = cli.summarize(results, {"formal_by_task": {"popcount16": True, "async_fifo": False}})
    assert summary["pass@1_count"] == "2/4" and summary["solved_count"] == "3/4"
    assert summary["per_task"]["async_fifo"]["formal_enabled"] is False
    assert summary["per_task"]["popcount16"]["formal_enabled"] is True
    assert summary["by_verification"] == {
        "formal": {"tasks": ["popcount16"], "episodes": 2, "errors": 0,
                   "pass@1_count": "1/2", "solved_count": "2/2"},
        "simulation_only": {"tasks": ["async_fifo"], "episodes": 2, "errors": 1,
                            "pass@1_count": "1/2", "solved_count": "1/2"},
    }


@pytest.mark.parametrize("no_formal", [False, True])
def test_run_records_effective_verification_mode(no_formal, monkeypatch, tmp_path):
    def run_episode(env_kwargs, agent_name, agent_kwargs, task_id):
        return episode(task_id, first=True, solved=True)

    monkeypatch.setattr(cli, "run_episode", run_episode)
    monkeypatch.setattr(cli, "_git_commit", lambda: "testing")
    monkeypatch.setattr(cli, "tool_versions", dict)
    file = tmp_path / "run.json"
    args = ["run", "--tasks", "popcount16,async_fifo", "--out", str(file)]
    assert cli.main(args + (["--no-formal"] if no_formal else [])) == 0
    summary = json.loads(file.read_text())["summary"]
    assert summary["formal_by_task"] == {"popcount16": not no_formal, "async_fifo": False}
    simulation = summary["by_verification"]["simulation_only"]
    assert simulation["episodes"] == (2 if no_formal else 1)


def test_report_renders_groups_and_legacy_files(tmp_path, capsys):
    results = [episode("popcount16", solved=True), episode("async_fifo", first=True, solved=True)]
    meta = {"agent": "replay", "max_turns": 3, "git_commit": "abcd", "tools": {"yosys": "Yosys"}}
    modern, legacy = tmp_path / "modern.json", tmp_path / "legacy.json"
    grouped = cli.summarize(results, {**meta, "formal_by_task": {"popcount16": True, "async_fifo": False}})
    modern.write_text(json.dumps({"summary": grouped}))
    old_summary = cli.summarize(results, {**meta, "model": "historical"})
    old_summary.pop("by_verification")
    legacy.write_text(json.dumps({"summary": old_summary}))
    assert cli.main(["report", str(modern), str(legacy)]) == 0
    report = capsys.readouterr().out
    assert "| replay (feedback full) | Formal enabled | 1 (0) | 0/1 | 1/1 |" in report
    assert "| replay (feedback full) | Simulation only | 1 (0) | 1/1 | 1/1 |" in report
    assert "| historical (feedback full) | 2 (0) |" in report
    assert report.count("(simulation only)") == 1
    assert "formal check passed where enabled" in report


def test_paired_report_separates_discordant_outcomes(tmp_path):
    tasks = {"popcount16": True, "async_fifo": False}
    formal_win = episode("popcount16", solved=True)
    sim_win = episode("async_fifo", solved=True)
    shared_error = {**episode("async_fifo", error="before attempt"),
                    "shared_first": {"error": "before attempt"}}
    table = cli.paired_table(
        {"full": [formal_win, episode("async_fifo"), shared_error],
         "none": [episode("popcount16"), sim_win, shared_error]},
        ("full", "none"), tasks,
    )
    assert table["discordant_pairs"] == 2
    assert table["by_verification"]["formal"]["outcomes"]["only_full"] == 1
    sim = table["by_verification"]["simulation_only"]
    assert sim["outcomes"]["only_none"] == 1 and sim["outcomes"]["errored"] == 1

    script = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "summary.py"
    spec = importlib.util.spec_from_file_location("ci_summary", script)
    ci_summary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ci_summary)
    (tmp_path / "replay__paired.json").write_text(json.dumps({"meta": {"agent": "replay"}, "paired": table}))
    report = ci_summary.report(str(tmp_path))
    assert "| replay | Formal enabled | 1 | 0 | 1 | 0 | 0 | 0 | 1 | 1 | 1.0 |" in report
    assert "| replay | Simulation only | 2 | 0 | 0 | 1 | 0 | 1 | 1 | 1 | 1.0 |" in report
