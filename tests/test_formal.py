"""Formal equivalence checking against the reference design."""
import dataclasses

import pytest

from rtlgym import load_task
from rtlgym.formal import check_equivalence, format_counterexample, parse_trace

pytestmark = pytest.mark.needs_tools


def test_combinational_proof_is_complete_and_gives_exact_counterexample(tmp_path):
    task = load_task("popcount16")
    ok = check_equivalence(task, task.candidates_dir / "good_loop.sv", tmp_path / "ok")
    assert ok.status == "pass" and ok.complete

    bad = check_equivalence(task, task.candidates_dir / "bug_width.sv", tmp_path / "bad")
    assert bad.status == "fail" and bad.first_mismatch == 1
    sig = bad.trace[0]["signals"]
    x = int(sig["in_x"]["dec"])
    assert int(sig["gold_count"]["dec"]) == bin(x).count("1")      # the reference is right
    assert int(sig["gate_count"]["dec"]) != int(sig["gold_count"]["dec"])
    assert "<-- differs" in format_counterexample(bad)


def test_rare_input_escape_is_found(tmp_path):
    task = load_task("popcount16")
    r = check_equivalence(task, task.candidates_dir / "escape_rare_input.sv", tmp_path)
    assert r.status == "fail"
    assert r.trace[0]["signals"]["in_x"]["hex"] == "beef"


def test_sequential_counterexample_starts_from_reset(tmp_path):
    task = load_task("fifo_sync")
    r = check_equivalence(task, task.candidates_dir / "bug_full_flag.sv", tmp_path)
    assert r.status == "fail" and not r.complete
    assert r.params == {"W": 2, "DEPTH": 4}
    assert r.trace[0]["signals"]["in_rst"]["dec"] == "1"           # reset in cycle 1
    assert all(s["signals"]["in_rst"]["dec"] == "0" for s in r.trace[1:])
    mism = next(s for s in r.trace if s["step"] == r.first_mismatch)["signals"]
    assert mism["gold_full"]["dec"] != mism["gate_full"]["dec"]


def test_uart_reference_is_equivalent_over_a_full_frame(tmp_path):
    task = load_task("uart_tx")
    assert task.formal["depth"] >= 44     # one 40-cycle frame plus the end of busy
    r = check_equivalence(task, task.candidates_dir / "good_shift.sv", tmp_path)
    assert r.status == "pass"


def test_interface_mismatch_is_reported_not_crashed(tmp_path):
    src = tmp_path / "cand.sv"
    src.write_text("module popcount16(input logic [15:0] x, output logic [3:0] count);\n"
                   "  assign count = x[3:0];\nendmodule\n")
    task = load_task("popcount16")
    r = check_equivalence(task, src, tmp_path / "w")
    assert r.status in ("error", "fail")


def test_formal_timeout_is_reported(tmp_path):
    task = load_task("fifo_sync")
    task = dataclasses.replace(task, formal={**task.formal, "depth": 40, "params": {}})
    r = check_equivalence(task, task.ref_path, tmp_path, timeout_s=1)
    assert r.status == "timeout"


def test_trace_parser_ignores_unrelated_lines():
    log = """Import show expression: \\in_x
  \\gate_count                0         0               00000
  \\gold_count               16        10               10000
  \\in_x                  65535      ffff    1111111111111111
  \\trigger                   1         1                   1
"""
    trace = parse_trace(log)
    assert len(trace) == 1 and trace[0]["signals"]["trigger"]["dec"] == "1"


def test_formal_timeout_can_be_set_per_task(monkeypatch, tmp_path):
    from rtlgym import formal
    from rtlgym.task import load_task
    seen = {}

    def fake_run(cmd, cwd, timeout_s, env=None):
        seen["timeout_s"] = timeout_s
        raise RuntimeError("stop here")

    monkeypatch.setattr(formal, "run", fake_run)
    task = load_task("noc_router5")
    assert task.formal["timeout_s"] == 240
    try:
        formal.check_equivalence(task, task.ref_path, tmp_path)
    except RuntimeError:
        pass
    assert seen["timeout_s"] == 240 + 15      # tool limit plus the subprocess margin
