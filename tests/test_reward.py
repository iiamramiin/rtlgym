import pytest

from rtlgym.evaluator import EvalResult
from rtlgym.reward import RewardWeights, compute_reward, ppa_score


def result(**kw):
    base = dict(task_id="t", code_sha="x", static_ok=True, compile_ok=True, lint_ok=True,
                synth_ok=True, tests_total=4, tests_passed=4, cells=100, depth=10, latches=0,
                ref_cells=100, ref_depth=10, formal_status="pass", sim_complete=True)
    base.update(kw)
    return EvalResult(**base)


def test_weights_sum_to_one():
    w = RewardWeights()
    assert w.compile + w.lint + w.functional + w.ppa == pytest.approx(1.0)


def test_static_or_compile_failure_is_zero():
    assert compute_reward(result(static_ok=False))[0] == 0.0
    assert compute_reward(result(compile_ok=False))[0] == 0.0


def test_matching_reference_scores_080_of_ppa_bonus():
    score, b = compute_reward(result())
    assert b["ppa"] == pytest.approx(0.15 * 0.8)
    assert score == pytest.approx(0.97)


def test_beating_reference_by_headroom_gets_full_score():
    score, _ = compute_reward(result(cells=80, depth=8))
    assert score == pytest.approx(1.0)


def test_reward_is_monotonic_in_tests_passed():
    scores = [compute_reward(result(tests_passed=k))[0] for k in range(5)]
    assert scores == sorted(scores) and len(set(scores)) == 5


def test_no_ppa_bonus_unless_all_tests_pass():
    _, b = compute_reward(result(tests_passed=3, cells=10))
    assert b["ppa"] == 0.0


def test_non_synthesizable_halves_functional_credit():
    _, b = compute_reward(result(synth_ok=False))
    assert b["functional"] == pytest.approx(0.35) and b["ppa"] == 0.0


def test_latch_penalty_and_no_ppa():
    _, b = compute_reward(result(latches=2))
    assert b["penalty"] == pytest.approx(-0.05) and b["ppa"] == 0.0


def test_lint_credit_decays_with_warnings():
    lint = [compute_reward(result(lint_warnings=["W"] * n))[1]["lint"] for n in (0, 1, 5, 9)]
    assert lint[0] == pytest.approx(0.05) and lint[0] > lint[1] > lint[2] == lint[3] == 0.0


def test_ppa_score_bounded():
    w = RewardWeights()
    assert ppa_score(1, 1, 1000, 100, w) == pytest.approx(1.0)
    assert 0.0 < ppa_score(1000, 100, 10, 1, w) < 0.05


def test_score_bounded_zero_one():
    for kw in ({}, {"latches": 5, "tests_passed": 0, "lint_ok": False}, {"cells": 1}):
        s, _ = compute_reward(result(**kw))
        assert 0.0 <= s <= 1.0


def test_test_escape_is_penalized_and_gets_no_bonus():
    score, b = compute_reward(result(formal_status="fail"))
    assert b["ppa"] == 0.0 and b["penalty"] == pytest.approx(-0.10)
    assert score == pytest.approx(0.75)


def test_formal_failure_with_failing_tests_adds_no_extra_penalty():
    _, b = compute_reward(result(formal_status="fail", tests_passed=2))
    assert b["penalty"] == 0.0


def test_bonus_needs_formal_pass_or_disabled():
    for status, expect_bonus in (("pass", True), ("disabled", True), ("error", False),
                                 ("timeout", False)):
        _, b = compute_reward(result(formal_status=status))
        assert (b["ppa"] > 0) == expect_bonus, status


def test_missing_depth_metric_earns_no_depth_credit():
    from rtlgym.reward import RewardWeights, ppa_score
    w = RewardWeights()
    assert ppa_score(100, None, 100, 10, w) == pytest.approx(w.area_vs_depth * 0.8)


def test_bonus_withheld_when_simulation_incomplete_or_interface_wrong():
    for kw in ({"sim_complete": False}, {"interface_errors": ["missing port 'x'"]},
               {"synth_ok": False}, {"latches": 1}):
        _, b = compute_reward(result(**kw))
        assert b["ppa"] == 0.0, kw
