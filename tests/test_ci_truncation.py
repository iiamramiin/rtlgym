# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Keep output-limit failures separate from checker and compiler errors in CI."""

import json
import runpy
from pathlib import Path

REPORT = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "ci" / "summary.py"))["report"]


def _episode(kind, *, truncated=True, complete=False):
    name = {"design": "dut", "repair": "repair_dut", "verify": "verify_dut"}[kind]
    module = "rtl_checker" if kind == "verify" else "dut"
    code = f"module {module}(input x);"
    if complete:
        code += " endmodule"
    else:
        code = "```systemverilog\n" + code
    turn = {"turn": 1, "score": 0.0, "reward": 0.0, "grade_s": 0.1, "cached": False,
            "code": code, "solved": False, "frontend_errors": ["compile"],
            "test_escape": False}
    row = {"task": name, "task_kind": kind, "error": None, "turns": 1,
           "pass@1": False, "pass@1_tests_only": False, "solved": False,
           "test_escapes": 0, "inconclusive": 0, "first_score": 0.0,
           "best_score": 0.0, "return": 0.0, "usage": {"calls": 1, "truncated": int(truncated)},
           "trajectory": [turn]}
    if kind == "verify":
        details = {"status": "invalid", "caught": 0, "mutants_total": 0,
                   "weighted_caught": 0.0, "families": {}}
        row["verification"] = turn["verification"] = details
    return row


def _write(root, rows, **summary):
    path = root / "model__full.json"
    path.write_text(json.dumps({
        "summary": {"model": "example", "feedback": "full", **summary}, "episodes": rows,
    }))
    return path


def test_ci_refreshes_archived_truncation_in_every_task_kind_without_writing(tmp_path):
    rows = [_episode(kind) for kind in ("design", "repair", "verify")]
    path = _write(tmp_path, rows, frontend_failure_attempts=3)
    before = path.read_bytes()
    output = REPORT(str(tmp_path))
    assert path.read_bytes() == before
    assert "**Truncated attempts: 3**" in output
    assert "| Model | Feedback | Front-end failures | Resource failures | Truncated |" in output
    assert "| example | full | 0 | 0 | 3 |" in output
    for kind in ("design", "repair", "verify"):
        assert f"| example | full | {kind} | 1 (0) | 0/1 | 0/1 | 1 |" in output
    # The verification table retains the original zero reward, with no invalid-checker count.
    assert "| example | full | 1 (0) | 0 | 0 | 0 | 1 | 0/0 |" in output


def test_ci_does_not_relabel_complete_code_or_nontruncated_invalid_checkers(tmp_path):
    _write(tmp_path, [
        _episode("verify", complete=True),
        _episode("verify", truncated=False),
        _episode("design", complete=True),
    ])
    output = REPORT(str(tmp_path))
    assert "**Truncated attempts: 0**" in output
    assert "| example | full | 3 | 0 | 0 |" in output
    assert "| example | full | 2 (2) | 0 | 2 | 0 | 0 | 0/0 |" in output


def test_ci_keeps_truncation_aggregates_when_only_summary_is_available(tmp_path):
    _write(tmp_path, [], truncated_attempts=4, frontend_failure_attempts=0,
           resource_failure_attempts=0)
    output = REPORT(str(tmp_path))
    assert "**Truncated attempts: 4**" in output
    assert "| example | full | 0 | 0 | 4 |" in output


def test_archived_hard_pilot_reports_four_cutoffs_without_rewriting_files():
    archive = (Path(__file__).resolve().parents[1] / "results" / "claude" /
               "2026-11-19" / "verify-hard-pilot")
    before = {path.name: path.read_bytes() for path in archive.iterdir() if path.is_file()}
    output = REPORT(str(archive))
    assert {path.name: path.read_bytes() for path in archive.iterdir() if path.is_file()} == before
    assert "**Truncated attempts: 4**" in output
    assert "| claude-haiku-5-5 | full | verify | 6 (0) | 2/6 | 2/6 | 4 |" in output
    assert "| claude-sonnet-5-5 | full | verify | 6 (0) | 6/6 | 6/6 | 0 |" in output
    # Check the verification table's named failure categories, independently of
    # whether the grader retained mutant metadata on the four partial sources.
    row = next(line for line in output.splitlines()
               if line.startswith("| claude-haiku-5-5 | full | 6 ("))
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    assert cells[3:7] == ["0", "0", "0", "4"]
