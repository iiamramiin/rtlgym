# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Check initialized history through the complete simulation and formal grader."""

import pytest

from rtlgym import evaluate, load_task
from rtlgym.env import format_feedback


@pytest.mark.needs_tools
@pytest.mark.parametrize("initial", [0, 1])
@pytest.mark.parametrize("form", ["declaration", "block"])
def test_initialized_monitor_starts_identically_in_simulation_and_formal(initial, form):
    declaration = f"reg valid = 1'b{initial};" if form == "declaration" else (
        f"reg valid; initial begin valid = 1'b{initial}; end"
    )
    expected = "rst" if initial else "!rst"
    source = f"""module rtl_checker(input clk, rst, input [3:0] req, gnt);
    {declaration}
    always @(posedge clk) begin
        assert(valid == {expected});
        valid <= 1'b{1-initial};
    end
endmodule
"""
    result = evaluate(load_task("verify_rr_arbiter4"), source, use_cache=False)
    details = result.verification
    assert details["status"] == "pass" and result.score == 0, result.to_dict()
    assert details["caught"] == 0
    assert all(target["formal"] == "pass" for target in details["targets"])
    assert all(target["sim_complete"] and not target["sim_failed"] for target in details["targets"])


@pytest.mark.needs_tools
def test_initial_value_is_not_replaced_with_an_assumed_zero():
    source = """module rtl_checker(input clk, rst, input [3:0] req, gnt);
    reg valid = 1'b1;
    always @(posedge clk) begin
        assert(valid == !rst);
        valid <= 1'b1;
    end
endmodule
"""
    result = evaluate(load_task("verify_rr_arbiter4"), source, use_cache=False)
    assert result.verification["status"] == "false_alarm" and result.score == 0
    assert result.verification["false_alarm_trace"]
    assert result.verification["targets"][0]["sim_failed"]


@pytest.mark.needs_tools
def test_invalid_checker_feedback_uses_plain_language():
    source = """module rtl_checker(input [15:0] x, input [4:0] count);
    always @* begin
        #1;
        assert(count == 0);
    end
endmodule
"""
    result = evaluate(load_task("verify_popcount16"), source, use_cache=False)
    assert result.verification["status"] == "invalid"
    feedback = format_feedback(result)
    assert "delay" in feedback.lower() or "timing" in feedback.lower()
    assert "Unsupported statement" not in feedback


def test_verification_specs_publish_the_system_prompt_rules():
    from rtlgym.agents.claude import VERIFY_SYSTEM_PROMPT

    rules = VERIFY_SYSTEM_PROMPT.split("\n", 1)[1]
    for task_id in ("verify_popcount16", "verify_rr_arbiter4", "verify_fifo_sync"):
        assert rules in load_task(task_id).spec
    for phrase in ("constant declaration initializer", "initial block", "$countones", "$onehot",
                   "$onehot0", "all bits initialized", "Do not drive observed ports"):
        assert phrase in rules


def test_checker_cache_version_is_separate_from_design_and_repair(monkeypatch):
    from rtlgym import evaluator, verify
    from rtlgym.reward import RewardWeights

    monkeypatch.setattr(evaluator, "_versions", lambda: {})
    task = load_task("verify_popcount16")
    manifest = verify.load_manifest(task)
    code = task.ref_path.read_text()
    old_verify = verify._cache_key(task, code, manifest)
    legacy = [load_task(task_id) for task_id in ("popcount16", "repair_popcount16")]
    old_legacy = [evaluator._cache_key(t, t.ref_path.read_text(), RewardWeights(), True)
                  for t in legacy]
    monkeypatch.setattr(verify, "VERIFY_GRADER_VERSION", "future-test-version")
    assert verify._cache_key(task, code, manifest) != old_verify
    assert [evaluator._cache_key(t, t.ref_path.read_text(), RewardWeights(), True)
            for t in legacy] == old_legacy
