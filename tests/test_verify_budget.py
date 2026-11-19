# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Attempt deadlines bound successive local tools without leaking across workers."""

import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from rtlgym import tools


def test_runtime_budget_covers_successive_tools_and_resets(tmp_path):
    command = [sys.executable, "-c", "import time; time.sleep(1)"]
    with tools.runtime_budget(0.1):
        first = tools.run(command, tmp_path, 3)
        second = tools.run(command, tmp_path, 3)
    assert first.timed_out and second.timed_out
    assert second.elapsed_s == 0 and "budget exhausted" in second.log
    assert tools.run([sys.executable, "-c", "print(1)"], tmp_path, 3).ok


def test_runtime_budget_isolated_between_parallel_attempts(tmp_path):
    def attempt(seconds, name):
        with tools.runtime_budget(seconds):
            return tools.run([sys.executable, "-c", "import time; time.sleep(0.15)"],
                             tmp_path / name, 3)

    with ThreadPoolExecutor(max_workers=2) as pool:
        short = pool.submit(attempt, 0.05, "short")
        long = pool.submit(attempt, 3, "long")
        assert short.result().timed_out
        assert long.result().ok


@pytest.mark.needs_tools
def test_verification_deadline_is_inconclusive_without_cached_reward():
    from rtlgym import evaluate, evaluator, load_task

    task = load_task("verify_rr_arbiter4")
    task = replace(task, verify={**task.verify, "max_grading_s": 0.000001})
    result = evaluate(task, task.ref_path.read_text())
    assert result.inconclusive and result.score == 0 and not result.accepted, result.to_dict()
    assert not list(evaluator.CACHE_DIR.glob("*.json"))


def test_an_unspecified_nested_budget_retains_the_outer_deadline(tmp_path):
    with tools.runtime_budget(0.05) as outer:
        with tools.runtime_budget(None) as inner:
            assert inner == outer
            result = tools.run([sys.executable, "-c", "import time; time.sleep(1)"], tmp_path, 3)
    assert result.timed_out
