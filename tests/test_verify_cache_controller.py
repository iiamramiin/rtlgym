# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Transaction checkers must tolerate legal cache timing and inactive payloads."""

import pytest

from rtlgym import evaluate, load_task
from rtlgym.verify import load_manifest


def test_cache_contract_corpus_records_distinct_legal_timing_choices():
    task = load_task("verify_cache_controller")
    manifest = load_manifest(task)
    assert len(manifest["correct_designs"]) >= 3
    assert len(manifest["mutants"]) >= 10
    assert {entry["freedom"]["HIT_DELAY"] for entry in manifest["correct_designs"]} == {1, 2}
    assert any(entry["freedom"].get("MISS_DELAY") == 2 for entry in manifest["correct_designs"])
    assert any(entry["freedom"].get("IDLE_PATTERN") == 3 for entry in manifest["correct_designs"])
    assert all(check["status"] == "different" for check in manifest["qualification"]["pairwise_checks"])
    assert len(manifest["qualification"]["correct_design_checks"]) == 3
    assert all(check["status"] == "different" for check in manifest["qualification"]["correct_design_checks"])


@pytest.mark.needs_tools
def test_cache_hand_checker_tolerates_all_legal_variants_and_catches_mutants():
    task = load_task("verify_cache_controller")
    result = evaluate(task, task.ref_path.read_text(), use_cache=False)
    detail = result.verification
    assert result.accepted and result.score == 1, result.to_dict()
    assert detail["caught"] == detail["mutants_total"] >= 10
    positives = [target for target in detail["targets"] if target["kind"] == "positive"]
    assert len(positives) >= 4 and all(target["formal"] == "pass" for target in positives)
    assert detail["grading_s"] < 60


@pytest.mark.needs_tools
@pytest.mark.parametrize("candidate", ["bug_cycle_exact.sv", "bug_idle_payload.sv"])
def test_overconstrained_cache_checker_false_alarms_on_legal_freedom(candidate):
    task = load_task("verify_cache_controller")
    source = (task.candidates_dir / candidate).read_text()
    result = evaluate(task, source, use_cache=False)
    assert result.verification["status"] == "false_alarm", result.to_dict()
    assert result.score == 0 and not result.accepted
    # The immediate reference is legal too; rejecting another legal behavior
    # invalidates this checker rather than a bug in its data scoreboard.
    targets = result.verification["targets"]
    assert targets[0]["formal"] == "pass"
    assert any(target["formal"] == "fail" for target in targets[1:])
    assert result.verification["false_alarm_trace"]
