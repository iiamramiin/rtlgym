# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Check the CI Markdown report with both current and archived results."""

import json
import runpy
from pathlib import Path

REPORT = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "ci" / "summary.py"))["report"]


def write_result(root, name, result):
    (root / name).write_text(json.dumps(result))


def test_legacy_reports_keep_their_tables(tmp_path):
    write_result(tmp_path, "model__full.json", {
        "summary": {"model": "example", "feedback": "full", "usage": {"calls": 2}},
        "episodes": [{"task": "edge_detect", "solved": True}],
    })
    write_result(tmp_path, "model__paired.json", {
        "meta": {"model": "example"},
        "paired": {
            "episodes": 1,
            "outcomes": {"both": 1, "only_full": 0, "only_none": 0, "neither": 0},
            "discordant_pairs": 0,
            "shared_first": {"calls": 1},
            "rows": [{"task": "edge_detect", "outcome": "both"}],
        },
    })
    output = REPORT(str(tmp_path))
    assert "### Paired outcomes (same first attempt in both arms)" in output
    assert "| example | 3 | 0 | 0 |" in output
    assert "by task kind" not in output
    assert "Repair edit size" not in output


def test_raw_mixed_results_report_repair_attempts_and_errors(tmp_path):
    write_result(tmp_path, "model__full.json", {
        "summary": {"model": "example", "feedback": "full"},
        "episodes": [
            {"task": "edge_detect", "pass@1": True, "solved": True,
             "trajectory": [{"lines_changed": 99, "solved": True}]},
            {"task": "repair_a", "task_kind": "repair", "pass@1": False, "solved": True,
             "trajectory": [
                 {"lines_changed": 0, "solved": False},
                 {"lines_changed": 12, "solved": False},
                 {"lines_changed": 2, "solved": True},
             ]},
            {"task": "repair_b", "task_kind": "repair", "pass@1": False, "solved": False,
             "trajectory": [{"lines_changed": 20, "solved": False}, {"solved": False}]},
            {"task": "repair_b", "task_kind": "repair", "error": "request failed", "trajectory": []},
        ],
    })
    write_result(tmp_path, "model__paired.json", {
        "meta": {"model": "example"},
        "paired": {
            "episodes": 4,
            "outcomes": {"both": 1, "only_full": 1, "only_none": 0, "neither": 1, "errored": 1},
            "discordant_pairs": 1,
            "rows": [
                {"task": "edge_detect", "outcome": "both"},
                {"task": "repair_a", "task_kind": "repair", "outcome": "only_full"},
                {"task": "repair_b", "task_kind": "repair", "outcome": "neither"},
                {"task": "repair_b", "task_kind": "repair", "outcome": "errored"},
            ],
        },
    })
    output = REPORT(str(tmp_path))
    assert "| example | full | design | 1 (0) | 1/1 | 1/1 |" in output
    assert "| example | full | repair | 3 (1) | 0/3 | 1/3 |" in output
    assert "| example | full | 7 (n=4) | 2 (n=1) |" in output
    assert "| example | repair | 3 | 0 | 1 | 0 | 1 | 1 |" in output


def test_summary_kind_aggregates_work_without_raw_rows(tmp_path):
    write_result(tmp_path, "model__none.json", {
        "summary": {
            "model": "example",
            "feedback": "none",
            "by_kind": {
                "repair": {"episodes": 2, "errors": 1, "pass@1_count": "0/2", "solved_count": "0/2",
                           "lines_changed": {"attempts": 1, "median": 0, "accepted_attempts": 0,
                                             "accepted_median": None}},
            },
        },
    })
    output = REPORT(str(tmp_path))
    assert "| example | none | repair | 2 (1) | 0/2 | 0/2 |" in output
    assert "| example | none | 0 (n=1) | — (n=0) |" in output
