# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""The gearbox checker grades stream contracts rather than exact scheduling."""

import pytest

from rtlgym import evaluate, load_task
from rtlgym.verify import load_manifest


def test_gearbox_corpus_records_contract_and_timing_freedom():
    task = load_task("verify_gearbox_16to12")
    manifest = load_manifest(task)
    assert task.verify["params"] == {"UNIT_W": 2}
    assert len(manifest["mutants"]) >= 10
    assert len(manifest["correct_designs"]) >= 3
    assert len({entry["family"] for entry in manifest["mutants"]}) >= 5
    assert all(entry["origin"].startswith("generated:") and entry["operator"]
               for entry in manifest["mutants"])
    qualification = manifest["qualification"]
    assert all(check["status"] == "pass" for check in qualification["correct_design_checks"])
    assert len(qualification["timing_freedom_checks"]) == len(manifest["correct_designs"])
    assert all(check["status"] == "different" and check["witness"]
               for check in qualification["timing_freedom_checks"])
    count = len(manifest["mutants"])
    assert len(qualification["pairwise_checks"]) >= count * (count - 1) // 2
    assert all(check["status"] == "different" for check in qualification["pairwise_checks"])


@pytest.mark.needs_tools
def test_gearbox_hand_checker_accepts_freedom_and_catches_all_contract_mutants():
    task = load_task("verify_gearbox_16to12")
    result = evaluate(task, task.ref_path.read_text(), use_cache=False)
    assert result.accepted and result.score == 1, result.to_dict()
    details = result.verification
    assert details["caught"] == details["mutants_total"] >= 10
    assert all(t["formal"] == ("pass" if t["kind"] == "positive" else "fail")
               for t in details["targets"])
    assert all(t["sim_complete"] and not t["sim_failed"]
               for t in details["targets"] if t["kind"] == "positive")


@pytest.mark.needs_tools
def test_copying_eager_gearbox_timing_raises_a_false_alarm_on_correct_variant():
    task = load_task("verify_gearbox_16to12")
    source = (task.candidates_dir / "bug_cycle_exact.sv").read_text()
    result = evaluate(task, source, use_cache=False)
    assert result.verification["status"] == "false_alarm", result.to_dict()
    assert result.score == 0 and not result.accepted
    positives = result.verification["targets"]
    assert positives[0]["formal"] == "pass"
    assert any(t["formal"] == "fail" for t in positives[1:])
