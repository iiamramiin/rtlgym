# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Exercise every repair starter and its accepted fixes through the real grader."""

import pytest

from rtlgym import RTLEnv, list_tasks, load_task

REPAIRS = [task_id for task_id in list_tasks() if load_task(task_id).kind == "repair"]


@pytest.mark.needs_tools
@pytest.mark.parametrize("task_id", REPAIRS)
def test_repair_starter_fails_and_parent_designs_fix_it(task_id):
    repair = load_task(task_id)
    parent = load_task(repair.parent_id)
    env = RTLEnv(max_turns=2, feedback="full")
    obs, _ = env.reset(task_id=task_id)
    diagnostics = obs["starter_feedback"]
    starter = obs["starter_code"]

    _, reward, terminated, truncated, info = env.step(starter)
    broken = info["eval"]
    assert broken.compile_ok and broken.sim_complete
    assert not broken.accepted and not broken.inconclusive
    assert broken.formal_status == "fail", broken.formal_message
    assert reward == 0 and info["lines_changed"] == 0
    assert not info["solved"] and not terminated and not truncated

    if repair.start_path.name.startswith("escape_"):
        assert broken.all_tests_pass and broken.test_escape
        assert broken.formal_counterexample and "Counterexample" in diagnostics
        assert "FAIL " not in diagnostics
    else:
        assert repair.start_path.name.startswith("bug_")
        assert not broken.all_tests_pass and broken.test_failures
        assert any(
            name in diagnostics and message and message.splitlines()[0][:300] in diagnostics
            for name, message in broken.test_failures.items()
        ), diagnostics

    alternatives = [path for path in parent.candidates() if path.name.startswith("good_")]
    assert alternatives
    for index, path in enumerate([parent.ref_path, *alternatives]):
        # The starter grade is reused inside this test's isolated cache.
        if index:
            env.reset(task_id=task_id)
        _, reward, terminated, truncated, info = env.step(path.read_text())
        result = info["eval"]
        assert result.accepted, (path.name, result.test_failures, result.formal_message, result.synth_log)
        assert info["solved"] and terminated and not truncated, path.name
        assert reward == pytest.approx(result.score - broken.score), path.name
        assert reward > 0 and info["lines_changed"] > 0, path.name
