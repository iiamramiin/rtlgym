# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Regression for the two-variable packed selection in archived router replies."""

import pytest

from rtlgym import evaluate, load_task, tools
from rtlgym.cli import _tasks_arg, _turn_record, summarize
from rtlgym.env import format_feedback
from rtlgym.task import DEFAULT_TASKS_ROOT

PACKED_SELECT = """
module popcount16(input logic [15:0] x, output logic [4:0] count);
    wire [3:0][3:0] req = x;
    always_comb begin
        count = '0;
        for (int d = 0; d < 4; d++)
            for (int idx = 0; idx < 4; idx++)
                count = count + {4'b0, req[d][idx]};
    end
endmodule
"""


@pytest.mark.needs_tools
def test_packed_select_simulates_after_icarus_frontend_retry(tmp_path):
    src = tmp_path / "packed.sv"
    src.write_text(PACKED_SELECT)
    task = load_task("popcount16")
    native = tools.compile_iverilog(src, task.top, tmp_path)
    r = evaluate(task, PACKED_SELECT, use_cache=False, keep_dir=tmp_path / "grade")
    assert r.accepted and r.all_tests_pass and r.formal_status == "pass", r.to_dict()
    assert not r.frontend_errors
    if native.ok:
        assert r.sim_frontend == "native"
    else:
        assert "Array index expressions must be constant" in native.log
        assert r.sim_frontend == "sv2v"
        assert (tmp_path / "grade" / "candidate_icarus.v").is_file()
        assert "compiled after sv2v" in format_feedback(r)
    rec = _turn_record(r, r.score, {"turn": 1, "solved": True, "grade_s": 0})
    assert rec["sim_frontend"] == r.sim_frontend
    ep = {"task": task.id, "error": None, "pass@1": True, "pass@1_tests_only": True,
          "solved": True, "test_escapes": 0, "first_score": r.score, "best_score": r.score,
          "turns": 1, "trajectory": [rec]}
    assert summarize([ep], {})["sim_frontend_fallback_attempts"] == int(not native.ok)


@pytest.mark.needs_tools
@pytest.mark.parametrize("broken", ["assign count = ;", "unknown_module item();"])
def test_real_compile_failures_still_stop_the_grade(broken):
    task = load_task("popcount16")
    code = f"module popcount16(input [15:0] x, output [4:0] count); {broken} endmodule"
    r = evaluate(task, code, use_cache=False)
    assert r.static_ok and not r.compile_ok and not r.accepted
    assert r.score == 0 and r.sim_frontend is None and not r.tests_total
    assert "Native Icarus" in r.compile_log


@pytest.mark.needs_tools
def test_identical_multiple_drivers_cannot_be_hidden_by_lowering(monkeypatch):
    task = load_task("popcount16")
    code = """module popcount16(input logic [15:0] x, output logic [4:0] count);
    assign count = {4'b0, x[0]};
    assign count = {4'b0, x[0]};
endmodule
"""
    monkeypatch.setattr(tools, "_convert_sv2v", lambda *a: pytest.fail("unexpected retry"))
    r = evaluate(task, code, use_cache=False)
    assert not r.compile_ok and not r.accepted and not r.tests_total
    assert "cannot have multiple drivers" in r.compile_log


def test_native_timeout_skips_retry(monkeypatch, tmp_path):
    failure = tools.ToolRun(False, None, "wall timeout", 30, timed_out=True)
    monkeypatch.setattr(tools, "compile_iverilog", lambda *a: failure)
    monkeypatch.setattr(tools, "_convert_sv2v", lambda *a: pytest.fail("unexpected retry"))
    src = tmp_path / "candidate.sv"
    assert tools.compile_simulation(src, "top", tmp_path) == (failure, src)


def test_task_group_selectors_preserve_explicit_selection():
    design = _tasks_arg("design", DEFAULT_TASKS_ROOT)
    repair = _tasks_arg("repair", DEFAULT_TASKS_ROOT)
    assert len(design) == 18 and len(repair) == 8
    assert set(design).isdisjoint(repair)
    assert set(design + repair).issubset(_tasks_arg("all", DEFAULT_TASKS_ROOT))
    assert _tasks_arg("repair_popcount16,popcount16", DEFAULT_TASKS_ROOT) == [
        "repair_popcount16", "popcount16",
    ]
