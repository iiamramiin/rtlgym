"""End-to-end grading of every task with real EDA tools.

This is the reward's own test suite: the reference must pass every hidden test
and the formal check, each correct alternative must pass both, each buggy
candidate must lose reward and fail the formal check, each test escape must pass
every test yet be caught by the formal check, and each adversarial candidate
must be blocked.
"""
import pytest

from rtlgym import evaluate, list_tasks, load_task

pytestmark = pytest.mark.needs_tools
TASKS = list_tasks()


def test_task_suite_is_populated():
    assert len(TASKS) >= 8


@pytest.mark.parametrize("task_id", TASKS)
def test_reference_passes_everything(task_id):
    task = load_task(task_id)
    r = evaluate(task, task.ref_path.read_text())
    assert r.tests_total >= 3 and r.tests_passed == r.tests_total, r.test_failures
    assert r.lint_ok and not r.lint_warnings, r.lint_warnings
    assert r.synth_ok and not r.latches
    assert not r.interface_errors
    assert r.formal_status == "pass", r.formal_message
    assert r.score >= 0.95


def candidates():
    for tid in TASKS:
        for path in load_task(tid).candidates():
            yield pytest.param(tid, path, id=f"{tid}/{path.stem}")


@pytest.mark.parametrize("task_id,path", list(candidates()))
def test_candidate_grades_match_their_label(task_id, path):
    task = load_task(task_id)
    ref = evaluate(task, task.ref_path.read_text())
    r = evaluate(task, path.read_text())
    kind = path.stem.split("_")[0]
    if kind == "good":
        assert r.tests_passed == r.tests_total and r.score >= 0.85, (r.test_failures, r.score)
        assert r.formal_status == "pass", r.formal_counterexample
    elif kind == "bug":
        assert r.tests_passed < r.tests_total
        assert r.score < ref.score - 0.2
        # Latches are outside what the formal check models; everything else must fail it.
        assert r.formal_status == ("error" if r.latches else "fail")
    elif kind == "escape":
        assert r.all_tests_pass and r.formal_status == "fail" and r.test_escape
        assert r.formal_counterexample and r.score < ref.score - 0.15
    elif kind in ("hack", "syntax"):
        assert r.score == 0.0
        assert r.formal_status == "skipped"
    elif kind == "nonsynth":
        assert not r.synth_ok and r.score < 0.5
        assert r.formal_status == "fail"
    else:
        pytest.fail(f"unlabeled candidate {path.name}")


def test_spec_never_leaks_hidden_material():
    for tid in TASKS:
        task = load_task(tid)
        assert "cocotb" not in task.spec and "test_" not in task.spec


def test_cache_returns_identical_result():
    task = load_task("popcount16")
    code = task.ref_path.read_text()
    first = evaluate(task, code)
    second = evaluate(task, code)
    assert second.cached and not first.cached
    assert second.score == first.score and second.breakdown == first.breakdown


def test_hanging_simulation_is_killed_and_scored_as_failure(tmp_path):
    import dataclasses
    import subprocess
    import time

    task = dataclasses.replace(load_task("popcount16"), sim_timeout_s=4)
    code = """module popcount16 (input logic [15:0] x, output logic [4:0] count);
    int k;
    always @(x) while (x != 16'hDEAD) k = k + 1;
    assign count = 5'd0;
endmodule
"""
    t0 = time.monotonic()
    work = tmp_path / "hang"
    r = evaluate(task, code, use_cache=False, keep_dir=work)
    assert time.monotonic() - t0 < 15
    assert r.sim_timed_out and r.tests_passed == 0 and r.score < 0.2
    leftover = subprocess.run(["pgrep", "-f", str(work)], capture_output=True, text=True).stdout
    assert leftover.strip() == "", "simulator process survived the timeout"
