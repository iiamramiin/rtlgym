# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Verification rewards require formal soundness and actual mutant witnesses."""

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from rtlgym import RTLEnv, evaluate, load_task
from rtlgym.env import format_feedback

TASKS = ("verify_popcount16", "verify_rr_arbiter4", "verify_fifo_sync")


@pytest.mark.needs_tools
@pytest.mark.parametrize("task_id", TASKS)
def test_hand_checker_proves_correct_designs_and_catches_every_mutant(task_id):
    task = load_task(task_id)
    result = evaluate(task, task.ref_path.read_text(), use_cache=False)
    detail = result.verification
    assert detail["mutants_total"] >= 10
    assert result.accepted and result.score == 1 and not result.inconclusive, result.to_dict()
    assert detail["caught"] == detail["mutants_total"]
    assert detail["assertions"] > 0 and detail["weighted_caught"] == 1
    assert all(target["formal"] == ("pass" if target["kind"] == "positive" else "fail")
               for target in detail["targets"])
    assert all(target["sim_complete"] for target in detail["targets"])
    assert all(not target["sim_failed"] for target in detail["targets"] if target["kind"] == "positive")
    assert format_feedback(result).startswith("Mutants caught:")


@pytest.mark.needs_tools
@pytest.mark.parametrize("task_id", TASKS)
def test_a_native_false_alarm_gets_zero_reward(task_id):
    task = load_task(task_id)
    result = evaluate(task, (task.candidates_dir / "bug_false_alarm.sv").read_text(), use_cache=False)
    assert result.verification["status"] == "false_alarm" and result.score == 0, result.to_dict()
    assert result.verification["false_alarm_trace"]
    assert not result.accepted and not result.inconclusive


@pytest.fixture
def controlled_grader(monkeypatch):
    from rtlgym import tools, verify

    task = load_task("verify_popcount16")
    monkeypatch.setattr(tools, "require_tools", lambda: None)
    monkeypatch.setattr(verify, "_ports", lambda *a: {"x": ("input", 16), "count": ("output", 5)})
    monkeypatch.setattr(verify, "validate_checker", lambda *a: SimpleNamespace(
        valid=True, reason="", source="validated", instrumented="instrumented", assert_count=1, state_bits=0,
    ))
    monkeypatch.setattr(verify, "simulate_checker", lambda *a: verify.Simulation(True, True, 0.1))
    return task, verify


def test_no_false_alarm_credit_comes_from_simulation(controlled_grader, monkeypatch):
    task, verify = controlled_grader
    monkeypatch.setattr(verify, "prove_checker", lambda *a: verify.Proof("pass", 0.1))
    result = verify.evaluate_checker(task, "submitted", use_cache=False)
    assert result.score == 0 and not result.accepted
    assert result.verification["status"] == "pass" and result.verification["caught"] == 0


def test_formal_false_alarm_overrules_a_clean_simulation(controlled_grader, monkeypatch):
    task, verify = controlled_grader
    monkeypatch.setattr(verify, "simulate_checker", lambda *a: verify.Simulation(True, False, 0.1))
    monkeypatch.setattr(verify, "prove_checker", lambda *a: verify.Proof("fail", 0.1, "cycle 2: x=f count=4"))
    result = verify.evaluate_checker(task, "submitted", use_cache=False)
    assert result.score == 0 and not result.accepted and not result.inconclusive
    assert result.verification["status"] == "false_alarm"
    assert "cycle 2" in format_feedback(result)
    assert "cycle 2" not in format_feedback(result, "summary")
    assert format_feedback(result, "none") == ""


@pytest.mark.parametrize("stop_at", [0, 3])
def test_unresolved_formal_has_zero_reward_and_never_caches(controlled_grader, monkeypatch, stop_at):
    from rtlgym import evaluator

    task, verify = controlled_grader
    calls = 0

    def prove(*_):
        nonlocal calls
        calls += 1
        return verify.Proof("inconclusive" if calls > stop_at else "pass", 0.1)

    monkeypatch.setattr(verify, "prove_checker", prove)
    result = verify.evaluate_checker(task, "submitted")
    assert result.inconclusive and not result.accepted and result.score == 0
    assert not list(evaluator.CACHE_DIR.glob("*.json"))


def test_family_weights_do_not_count_large_families_more(controlled_grader, monkeypatch):
    task, verify = controlled_grader
    manifest = verify.load_manifest(task)
    sizes = Counter(entry["family"] for entry in manifest["mutants"])
    family = min(sizes, key=sizes.get)
    caught_paths = {Path(entry["path"]).name for entry in manifest["mutants"] if entry["family"] == family}

    def prove(_task, design, *_):
        return verify.Proof("fail" if design.name in caught_paths else "pass", 0.1)

    monkeypatch.setattr(verify, "prove_checker", prove)
    result = verify.evaluate_checker(task, "submitted", use_cache=False)
    assert result.score == pytest.approx(round(1 / len(sizes), 4))
    assert result.verification["caught"] == sizes[family]
    assert "operator_xor" not in format_feedback(result)


def test_frozen_mutant_hashes_are_checked(tmp_path):
    from rtlgym.verify import _artifact

    mutant = tmp_path / "mutant.sv"
    mutant.write_text("changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        _artifact(tmp_path, {"path": mutant.name, "sha256": "0" * 64})
    with pytest.raises(ValueError, match="outside"):
        _artifact(tmp_path, {"path": "../escape.sv", "sha256": "0" * 64})


def test_manifest_records_generated_mutants_and_fifo_freedom():
    for task_id in TASKS:
        task = load_task(task_id)
        manifest = json.loads((task.root / "mutants.json").read_text())
        assert len(manifest["mutants"]) >= 10
        assert len(list((task.root / "mutants").glob("*.sv"))) == len(manifest["mutants"])
        assert any(m["origin"].startswith("generated:") for m in manifest["mutants"])
        assert manifest["qualification"]["excluded"] is not None
    fifo = load_task("verify_fifo_sync")
    manifest = json.loads((fifo.root / "mutants.json").read_text())
    assert manifest["profile"]["fifo_dout"] == "read_only"
    assert len(manifest["correct_designs"]) >= 3


def test_runtime_profile_changes_invalidate_the_checker_cache(controlled_grader):
    task, verify = controlled_grader
    manifest = verify.load_manifest(task)
    changed = replace(task, verify={**task.verify, "timeout_s": 7})
    assert verify._cache_key(task, "submitted", manifest) != verify._cache_key(changed, "submitted", manifest)


def test_mutated_artifact_cannot_reuse_a_warm_cache(controlled_grader, monkeypatch, tmp_path):
    import shutil

    task, verify = controlled_grader
    copied = tmp_path / "verify_popcount16"
    shutil.copytree(task.root, copied)
    task = replace(task, root=copied)
    monkeypatch.setattr(verify, "prove_checker", lambda *a: verify.Proof("pass", 0.1))
    assert not verify.evaluate_checker(task, "submitted").cached
    assert verify.evaluate_checker(task, "submitted").cached
    manifest = verify.load_manifest(task)
    mutant = copied / manifest["mutants"][0]["path"]
    mutant.write_text(mutant.read_text() + "\n// edited artifact\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify.evaluate_checker(task, "submitted")


@pytest.mark.needs_tools
def test_verify_environment_uses_reward_and_native_checker_without_conversion(monkeypatch):
    from rtlgym import tools

    native = tools.run

    def no_converter(command, *a, **kw):
        assert command[0] != "sv2v"
        return native(command, *a, **kw)

    monkeypatch.setattr(tools, "run", no_converter)
    task = load_task("verify_popcount16")
    env = RTLEnv(max_turns=1, use_cache=False)
    obs, _ = env.reset(task.id)
    assert obs["task_kind"] == "verify" and obs["top"] == "rtl_checker"
    _, reward, done, truncated, info = env.step(task.ref_path.read_text())
    assert reward == 1 and done and not truncated and info["solved"]


@pytest.mark.needs_tools
def test_copying_the_reference_idle_fifo_behavior_fails_on_a_correct_alternative():
    task = load_task("verify_fifo_sync")
    source = (task.candidates_dir / "bug_idle_hold.sv").read_text()
    result = evaluate(task, source, use_cache=False)
    detail = result.verification
    assert detail["status"] == "false_alarm" and result.score == 0, result.to_dict()
    assert detail["targets"][0]["formal"] == "pass"
    assert detail["targets"][-1]["formal"] == "fail"
    assert len(detail["targets"]) > 1
    feedback = format_feedback(result)
    assert detail["false_alarm_trace"] and "good_" not in feedback and "mutants/" not in feedback


@pytest.mark.needs_tools
def test_environment_validation_keeps_extra_unused_module_in_the_artifact():
    task = load_task("verify_popcount16")
    env = RTLEnv(max_turns=1)
    env.reset(task.id)
    artifact = task.ref_path.read_text() + "\nmodule extra; endmodule\n"
    _, reward, _, _, info = env.step(artifact)
    assert reward == 0 and info["eval"].verification["status"] == "invalid"


@pytest.mark.needs_tools
def test_formal_sampling_clock_has_the_rising_edge_value():
    task = load_task("verify_rr_arbiter4")
    code = """module rtl_checker(input clk, rst, input [3:0] req, gnt);
    always @(posedge clk) assert(clk);
endmodule
"""
    result = evaluate(task, code, use_cache=False)
    assert result.verification["status"] == "pass" and result.score == 0, result.to_dict()
