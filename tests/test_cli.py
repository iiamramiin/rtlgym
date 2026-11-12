"""CLI: run with the replay agent, save results, and render the Markdown report."""
import json

import pytest

from rtlgym.cli import main

pytestmark = pytest.mark.needs_tools


def test_run_and_report_roundtrip(tmp_path, capsys):
    out = tmp_path / "replay.json"
    assert main(["run", "--agent", "replay", "--tasks", "popcount16,edge_detect",
                 "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    s = data["summary"]
    assert s["episodes"] == 2 and s["errors"] == 0
    assert s["solved_within_turns"] == 1.0 and s["formal"] is True
    assert s["git_commit"] and s["tools"]["yosys"]
    assert set(s["per_task"]) == {"popcount16", "edge_detect"}
    capsys.readouterr()
    assert main(["report", str(out)]) == 0
    md = capsys.readouterr().out
    assert "| replay (feedback full) | 2 / 2 |" in md and "| popcount16 |" in md


def test_invalid_counts_are_rejected():
    for argv in (["run", "--samples", "0"], ["run", "--max-turns", "0"],
                 ["run", "--workers", "-1"]):
        with pytest.raises(SystemExit):
            main(argv)


def test_empty_task_selection_is_rejected():
    with pytest.raises(SystemExit):
        main(["run", "--tasks", " , "])
