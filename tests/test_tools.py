"""Tool execution: environment hygiene, output limits, and honest stage results."""
import sys

import pytest

from rtlgym import tools


def test_tool_env_drops_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-secret")
    env = tools.tool_env()
    assert "ANTHROPIC_API_KEY" not in env and "GITHUB_TOKEN" not in env and "PATH" in env
    r = tools.run([sys.executable, "-c", "import os; print(sorted(os.environ))"], tmp_path, 30)
    assert r.ok and "ANTHROPIC_API_KEY" not in r.log and "GITHUB_TOKEN" not in r.log


def test_output_is_captured_to_file_and_capped(tmp_path):
    r = tools.run([sys.executable, "-c", "import sys; sys.stdout.write('x' * 5_000_000)"],
                  tmp_path, 30)
    assert r.ok
    assert len(r.log) <= tools.CAPTURE_TAIL_BYTES + 64 and "[output truncated]" in r.log
    assert not list(tmp_path.glob(".*.out"))           # capture file cleaned up


def test_missing_tool_is_reported_not_raised(tmp_path):
    r = tools.run(["definitely-not-a-real-tool"], tmp_path, 5)
    assert not r.ok and r.returncode is None and "tool not found" in r.log


def test_lint_is_not_clean_when_the_tool_never_ran(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "run", lambda *a, **k: tools.ToolRun(False, None,
                                                                     "tool not found", 0.0))
    res = tools.lint_verilator(tmp_path / "x.sv", "x", tmp_path)
    assert not res.ok


def test_require_tools_raises_with_install_hint(monkeypatch):
    monkeypatch.setattr(tools, "_TOOLS_CHECKED", False)
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    with pytest.raises(tools.MissingToolError, match="apt-get install"):
        tools.require_tools()


def test_malformed_synthesis_statistics_fail_the_stage(monkeypatch, tmp_path):
    def fake_run(cmd, cwd, timeout_s, env=None):
        (cwd / "stat.json").write_text("{not json")
        return tools.ToolRun(True, 0, "", 0.1)
    monkeypatch.setattr(tools, "run", fake_run)
    res = tools.synth_yosys(tmp_path / "x.sv", "x", tmp_path)
    assert not res.ok and res.cells is None and "malformed" in res.log


def test_missing_tests_count_as_failures():
    total, passed, failures, complete = tools.account_tests(
        ["a", "b", "c"], {"a": None, "b": "assertion failed"})
    assert (total, passed, complete) == (3, 1, False)
    assert failures["b"] == "assertion failed" and "did not run" in failures["c"]


def test_expected_tests_come_from_the_testbench(tmp_path):
    tb = tmp_path / "test_x.py"
    tb.write_text("import cocotb\n\n@cocotb.test()\nasync def test_one(dut):\n    pass\n\n"
                  "@cocotb.test(timeout_time=5)\n@some_other_decorator\n"
                  "async def test_two(dut):\n    pass\n\nasync def helper(dut):\n    pass\n")
    assert tools.expected_tests(tb) == ["test_one", "test_two"]


# cocotb changed its JUnit failure attributes between 2.0 and 2.1; both must keep
# the message, or the agent only ever sees "failed".
JUNIT_2_1 = """<testsuites><testsuite name="t">
<testcase name="test_ok"/>
<testcase name="test_bad">
  <failure message="x=0xffff: count=0, expected 16" type="AssertionError">Traceback</failure>
</testcase>
<testcase name="test_skip"><skipped/></testcase>
</testsuite></testsuites>"""
JUNIT_2_0 = """<testsuites><testsuite name="t">
<testcase name="test_ok"/>
<testcase name="test_bad">
  <failure error_type="AssertionError" error_msg="x=0xffff: count=0, expected 16"/>
</testcase>
<testcase name="test_init"><failure msg="Test initialization failed"/></testcase>
<testcase name="test_text"><error>simulator crashed</error></testcase>
<testcase name="test_bare"><failure/></testcase>
</testsuite></testsuites>"""


@pytest.mark.parametrize("xml", [JUNIT_2_1, JUNIT_2_0], ids=["cocotb-2.1", "cocotb-2.0"])
def test_parse_junit_keeps_failure_messages(xml, tmp_path):
    p = tmp_path / "results.xml"
    p.write_text(xml)
    got = tools.parse_junit(p)
    assert got["test_ok"] is None
    assert got["test_bad"] == "x=0xffff: count=0, expected 16"


def test_parse_junit_fallbacks(tmp_path):
    p = tmp_path / "results.xml"
    p.write_text(JUNIT_2_0)
    got = tools.parse_junit(p)
    assert got["test_init"] == "Test initialization failed"
    assert got["test_text"] == "simulator crashed"   # message in the element text
    assert got["test_bare"] == "failed"               # nothing at all to report


def test_tool_versions_include_cocotb():
    v = tools.tool_versions()
    assert v["cocotb"] not in ("", "missing")


@pytest.mark.needs_tools
def test_real_simulation_reports_expected_vs_actual():
    """End to end with the installed cocotb: the failure must carry its message."""
    from rtlgym.evaluator import evaluate
    from rtlgym.task import load_task
    task = load_task("popcount16")
    r = evaluate(task, (task.root / "candidates" / "bug_width.sv").read_text(), use_cache=False)
    msgs = [m for m in r.test_failures.values() if m]
    assert msgs and any("expected" in m for m in msgs), r.test_failures
