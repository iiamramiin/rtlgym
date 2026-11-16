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
    assert r.formal_status == ("pass" if task.has_formal else "disabled"), r.formal_message
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
        assert r.formal_status == ("pass" if task.has_formal else "disabled"), r.formal_counterexample
    elif kind == "bug":
        assert r.tests_passed < r.tests_total
        assert r.score < ref.score - 0.2
        # Latches are outside what the formal check models; everything else must fail it.
        assert r.formal_status == (
            ("error" if r.latches else "fail") if task.has_formal else "disabled"
        )
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


def test_acceptance_predicate_matrix():
    from rtlgym.evaluator import EvalResult
    base = dict(task_id="t", code_sha="x", static_ok=True, compile_ok=True, synth_ok=True,
                latches=0, tests_total=3, tests_passed=3, sim_complete=True, formal_status="pass")
    assert EvalResult(**base).accepted
    assert EvalResult(**{**base, "formal_status": "disabled"}).accepted
    for change in ({"formal_status": "error"}, {"formal_status": "timeout"},
                   {"formal_status": "fail"}, {"sim_complete": False}, {"synth_ok": False},
                   {"latches": 2}, {"interface_errors": ["missing port"]},
                   {"tests_passed": 2}):
        r = EvalResult(**{**base, **change})
        assert not r.accepted, change
    assert EvalResult(**{**base, "formal_status": "timeout"}).inconclusive


def test_corrupt_cache_entry_is_regraded(monkeypatch, tmp_path):
    from rtlgym import evaluator
    task = load_task("popcount16")
    code = task.ref_path.read_text()
    first = evaluate(task, code)
    files = list(evaluator.CACHE_DIR.glob("*.json"))
    assert len(files) == 1
    files[0].write_text("{truncated")
    again = evaluate(task, code)
    assert not again.cached and again.score == first.score


def test_grader_version_change_invalidates_cache(monkeypatch):
    from rtlgym import evaluator
    task = load_task("popcount16")
    code = task.ref_path.read_text()
    evaluate(task, code)
    assert evaluate(task, code).cached
    monkeypatch.setattr(evaluator, "GRADER_VERSION", "test-bump")
    assert not evaluate(task, code).cached


def test_inconclusive_results_are_not_cached(tmp_path):
    import dataclasses

    from rtlgym import evaluator
    task = dataclasses.replace(load_task("popcount16"), sim_timeout_s=3)
    code = """module popcount16 (input logic [15:0] x, output logic [4:0] count);
    int k;
    always @(x) while (x != 16'hDEAD) k = k + 1;
    assign count = 5'd0;
endmodule
"""
    r = evaluate(task, code)
    assert r.inconclusive and not r.accepted
    assert r.tests_total == 3 and r.tests_passed == 0          # every expected test counted
    assert not list(evaluator.CACHE_DIR.glob("*.json"))


def test_retained_work_directory_can_be_reused(tmp_path):
    task = load_task("edge_detect")
    code = task.ref_path.read_text()
    for _ in range(2):
        r = evaluate(task, code, use_cache=False, keep_dir=tmp_path / "work")
        assert r.accepted


# Valid SystemVerilog that Icarus and Verilator accept but Yosys 0.33's parser rejects
# (a function with a local variable, a loop, and `return`). These cases exercise
# the exact native-parser fallback path without changing the fixture suite.
YOSYS_UNREADABLE = """module popcount16 (input logic [15:0] x, output logic [4:0] count);
    function automatic logic [4:0] pc(input logic [15:0] v);
        logic [4:0] n;
        n = '0;
        for (int i = 0; i < 16; i++) n = n + v[i];
        return n;
    endfunction
    assign count = pc(x);
endmodule
"""


@pytest.mark.parametrize("code", [
    YOSYS_UNREADABLE,
    YOSYS_UNREADABLE.replace("return n;", "return v == '0 ? 5'd0 : n;"),
    YOSYS_UNREADABLE.replace("v[i]", "v[int'(i)]").replace("return n;", "pc = n;"),
], ids=["return", "conditional-return", "int-cast"])
def test_sv2v_recovers_valid_systemverilog(code):
    r = evaluate(load_task("popcount16"), code, use_cache=False)
    assert r.accepted, (r.synth_log, r.formal_message, r.test_failures)
    assert r.synth_frontend == r.formal_frontend == "sv2v"
    assert not r.frontend_errors


def test_unresolved_parse_failure_is_reported_separately(monkeypatch):
    from rtlgym import tools
    from rtlgym.env import format_feedback

    original = tools.run

    def reject_conversion(cmd, cwd, timeout_s, env=None):
        if cmd[0] == "sv2v":
            return tools.ToolRun(False, 1, "converter syntax diagnostic", 0.01)
        return original(cmd, cwd, timeout_s, env=env)

    monkeypatch.setattr(tools, "run", reject_conversion)
    r = evaluate(load_task("popcount16"), YOSYS_UNREADABLE, use_cache=False)
    assert r.all_tests_pass and not r.accepted and not r.inconclusive
    assert set(r.frontend_errors) == {"synthesis", "formal"}
    assert "front end could not parse" in format_feedback(r)
    assert "converter syntax diagnostic" in format_feedback(r)


@pytest.mark.parametrize("passing", [True, False], ids=["all-tests-pass", "some-tests-fail"])
def test_synthesis_resource_stop_and_cache(monkeypatch, passing):
    from rtlgym import evaluator, tools
    from rtlgym.cli import _turn_record
    from rtlgym.env import format_feedback

    original = tools.run

    def stop_after_read(cmd, cwd, timeout_s, env=None):
        if cmd[0] == "yosys" and "-p" in cmd and "candidate.sv" in cmd[-1]:
            read_only = cmd[-1].split("; hierarchy", 1)[0]
            assert original([*cmd[:-1], read_only], cwd, timeout_s, env=env).ok
            return tools.ToolRun(False, -6, "terminate called after throwing std::bad_alloc", 0.1)
        return original(cmd, cwd, timeout_s, env=env)

    monkeypatch.setattr(tools, "run", stop_after_read)
    task = load_task("popcount16")
    path = task.ref_path if passing else task.candidates_dir / "bug_width.sv"
    r = evaluate(task, path.read_text())
    assert r.all_tests_pass is passing and r.sim_complete
    assert not r.accepted and r.inconclusive is passing
    assert not r.frontend_errors
    assert r.resource_failures == {"synthesis": "memory allocation failure"}
    assert "Synthesis: stopped by a resource limit" in format_feedback(r)
    assert bool(list(evaluator.CACHE_DIR.glob("*.json"))) is not passing
    turn = _turn_record(r, 0, {"turn": 1, "grade_s": 0.1, "solved": False})
    assert turn["resource_failures"] == r.resource_failures


def test_formal_resource_stop_is_inconclusive(monkeypatch):
    from rtlgym import evaluator, formal
    from rtlgym.env import format_feedback

    def stop_after_read(*args, **kwargs):
        return formal.FormalResult(status="error", resource_limit="CPU time limit")

    monkeypatch.setattr(formal, "check_equivalence", stop_after_read)
    task = load_task("popcount16")
    r = evaluate(task, task.ref_path.read_text())
    assert r.all_tests_pass and r.synth_ok and r.inconclusive and not r.accepted
    assert r.resource_failures == {"formal": "CPU time limit"}
    assert "Formal: stopped by a resource limit" in format_feedback(r)
    assert not list(evaluator.CACHE_DIR.glob("*.json"))
