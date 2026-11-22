# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""A paired first submission has one grade, including uncached unresolved grades."""

import pytest

from rtlgym import cli
from rtlgym.agents.base import Agent
from rtlgym.env import RTLEnv
from rtlgym.evaluator import EvalResult


class FirstAttemptAgent(Agent):
    def __init__(self):
        self.usage = {"calls": 0, "truncated": 0}

    def act(self, obs):
        self.usage["calls"] += 1
        return f"module {obs['top']}; // FIRST_ATTEMPT\nendmodule"


def _grade(task, accepted):
    result = EvalResult(task.id, "example", static_ok=True, compile_ok=True, lint_ok=True,
                        synth_ok=True, latches=0, tests_total=1, tests_passed=1,
                        sim_complete=True, formal_status="pass" if accepted else "timeout",
                        score=1.0 if accepted else 0.85)
    if not accepted:
        result.resource_failures = {"formal": "timeout"}
    if task.kind == "verify":
        result.score = 1.0 if accepted else 0.0
        result.verification = {"status": "pass" if accepted else "inconclusive",
                               "caught": int(accepted), "mutants_total": 1,
                               "weighted_caught": float(accepted), "families": {},
                               "false_alarm_trace": ""}
    return result


@pytest.mark.parametrize("task_id", ["popcount16", "repair_popcount16", "verify_popcount16"])
@pytest.mark.parametrize("accepted", [False, True])
def test_uncached_first_grade_is_evaluated_once_and_reused_in_both_arms(monkeypatch, task_id, accepted):
    evaluations, applied = [], []

    def evaluate(task, code, *args, **kwargs):
        assert kwargs["use_cache"] is False
        if "FIRST_ATTEMPT" not in code:  # repair reset grades its starter separately
            return EvalResult(task.id, "starter")
        evaluations.append(code)
        # A second evaluation would differ, exposing accidental regrading.
        return _grade(task, accepted if len(evaluations) == 1 else not accepted)

    original_grade, original_apply = RTLEnv._grade, RTLEnv._apply_grade

    def timed_grade(self, action):
        code, result, _ = original_grade(self, action)
        return code, result, 1.25

    def record_apply(self, code, result, grade_s):
        applied.append(result)
        return original_apply(self, code, result, grade_s)

    monkeypatch.setattr("rtlgym.env.evaluate", evaluate)
    monkeypatch.setattr(cli, "make_agent", lambda *_args, **_kwargs: FirstAttemptAgent())
    monkeypatch.setattr(RTLEnv, "_grade", timed_grade)
    monkeypatch.setattr(RTLEnv, "_apply_grade", record_apply)
    rows = cli.run_paired_episode({"max_turns": 1, "use_cache": False}, "stub", {}, task_id)

    assert len(evaluations) == 1
    assert len(applied) == 2 and applied[0] is applied[1]
    full, none = rows["full"], rows["none"]
    assert full["first_score"] == none["first_score"] == applied[0].score
    assert full["pass@1"] is none["pass@1"] is accepted
    for row in rows.values():
        assert row["solved"] is accepted
        assert row["inconclusive"] == int(not accepted)
        assert row["shared_first"]["grade_s"] == row["trajectory"][0]["grade_s"] == 1.25
        assert row["shared_first"]["usage"]["calls"] == 1 and row["usage"]["calls"] == 0
    assert full["trajectory"][0]["resource_failures"] == none["trajectory"][0]["resource_failures"]
    pair = cli.paired_table({arm: [row] for arm, row in rows.items()}, ("full", "none"))
    assert pair["shared_first"]["grade_s"] == 1.25  # actual work, counted once
    assert pair["shared_first"]["calls"] == 1
    assert pair["outcomes"]["both" if accepted else "neither"] == 1


@pytest.mark.parametrize("task_id", ["popcount16", "repair_popcount16", "verify_popcount16"])
def test_shared_grading_error_is_reported_in_both_arms_without_retrying(monkeypatch, task_id):
    calls = []

    def evaluate(task, code, *args, **kwargs):
        if "FIRST_ATTEMPT" not in code:
            return EvalResult(task.id, "starter")
        calls.append(code)
        raise RuntimeError("shared grading failed")

    monkeypatch.setattr("rtlgym.env.evaluate", evaluate)
    monkeypatch.setattr(cli, "make_agent", lambda *_args, **_kwargs: FirstAttemptAgent())
    rows = cli.run_paired_episode({"max_turns": 3, "use_cache": False}, "stub", {}, task_id)
    assert len(calls) == 1
    for row in rows.values():
        assert row["error"] == row["shared_first"]["error"] == "RuntimeError: shared grading failed"
        assert row["trajectory"] == [] and row["usage"]["calls"] == 0
        assert row["shared_first"]["usage"]["calls"] == 1
        assert row["shared_first"]["grade_s"] >= 0
    pair = cli.paired_table({arm: [row] for arm, row in rows.items()}, ("full", "none"))
    assert pair["outcomes"]["errored"] == 1 and pair["outcomes"]["neither"] == 0
