# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""AXI checkers must tolerate legal timing choices and still find protocol bugs."""

import pytest

from rtlgym import evaluate, load_task
from rtlgym.verify import load_manifest


def test_axi_corpus_contains_qualified_protocol_bugs_and_distinct_legal_schedules():
    task = load_task("verify_axi4_burst_slave")
    manifest = load_manifest(task)
    assert len(manifest["mutants"]) >= 10
    assert len(manifest["correct_designs"]) >= 3
    assert manifest["qualification"]["pairwise_behavioral_deduplication"]
    assert manifest["qualification"]["hand_checker_contract_gate"]
    assert all(entry["contract_proof"]["status"] == "fail" for entry in manifest["mutants"])
    assert all(entry["operator"]["before"] != entry["operator"]["after"]
               and entry["contract_witness"] and entry["witness"] for entry in manifest["mutants"])
    assert all(entry["contract_proof"]["status"] == "pass" and entry["freedom_witness"]
               for entry in manifest["correct_designs"])


@pytest.mark.needs_tools
def test_axi_hand_checker_accepts_every_legal_schedule_and_finds_all_mutants():
    task = load_task("verify_axi4_burst_slave")
    result = evaluate(task, task.ref_path.read_text(), use_cache=False)
    detail = result.verification
    assert result.accepted and result.score == 1, result.to_dict()
    assert detail["caught"] == detail["mutants_total"]
    assert all(target["formal"] == ("pass" if target["kind"] == "positive" else "fail")
               for target in detail["targets"])
    assert all(target["sim_complete"] for target in detail["targets"])
    assert all(not target["sim_failed"] for target in detail["targets"] if target["kind"] == "positive")


@pytest.mark.needs_tools
def test_cycle_exact_axi_ready_checker_false_alarms_on_a_legal_throttled_design():
    task = load_task("verify_axi4_burst_slave")
    source = (task.candidates_dir / "bug_cycle_exact.sv").read_text()
    result = evaluate(task, source, use_cache=False)
    detail = result.verification
    assert detail["status"] == "false_alarm" and result.score == 0, result.to_dict()
    assert detail["targets"][0]["formal"] == "pass"
    assert detail["targets"][1]["formal"] == "fail"
    assert detail["false_alarm_trace"] and not result.accepted


@pytest.mark.needs_tools
def test_axi_checker_detects_ready_during_the_first_reset_sample(tmp_path):
    from rtlgym import verify
    from rtlgym.verify_syntax import validate_checker

    task = load_task("verify_axi4_burst_slave")
    manifest = load_manifest(task)
    source = task.root / manifest["reference"]["path"]
    ports = verify._ports(task, source, tmp_path)
    validated = validate_checker(task.ref_path.read_text(), ports, tmp_path / "syntax", "clk", "rst")
    assert validated.valid, validated.reason
    checker = tmp_path / "checker.sv"
    checker.write_text(validated.source)
    bad = tmp_path / "bad_reset.sv"
    original = "assign s_axi_awready = inner_s_axi_awready && permit;"
    design = source.read_text()
    assert design.count(original) == 1
    bad.write_text(design.replace(original, "assign s_axi_awready = rst || (inner_s_axi_awready && permit);"))
    proof = verify.prove_checker(task, bad, checker, ports, tmp_path / "proof")
    assert proof.status == "fail" and "rst=1" in proof.trace, proof
