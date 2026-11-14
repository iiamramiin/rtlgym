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
    assert "| replay (feedback full) | 2 (0) | 0/2 (0%) |" in md and "| popcount16 |" in md
    assert s["pass@1_count"] == "0/2" and s["solved_count"] == "2/2"


def test_invalid_counts_are_rejected():
    for argv in (["run", "--samples", "0"], ["run", "--max-turns", "0"],
                 ["run", "--workers", "-1"]):
        with pytest.raises(SystemExit):
            main(argv)


def test_empty_task_selection_is_rejected():
    with pytest.raises(SystemExit):
        main(["run", "--tasks", " , "])


def test_paired_run_branches_one_first_attempt(tmp_path, capsys):
    out = tmp_path / "pair.json"
    assert main(["run", "--agent", "replay", "--tasks", "popcount16,edge_detect",
                 "--samples", "2", "--paired", "--out", str(out)]) == 0
    full = json.loads((tmp_path / "pair__full.json").read_text())
    none = json.loads((tmp_path / "pair__none.json").read_text())
    paired = json.loads((tmp_path / "pair__paired.json").read_text())["paired"]
    assert full["summary"]["feedback"] == "full" and none["summary"]["feedback"] == "none"
    assert full["summary"]["paired"] and full["summary"]["episodes"] == 4
    for ef, en in zip(full["episodes"], none["episodes"], strict=True):
        assert ef["task"] == en["task"]
        # Turn 1 is the same attempt in both arms.
        assert ef["trajectory"][0]["score"] == en["trajectory"][0]["score"]
        assert ef["pass@1"] == en["pass@1"] and ef["first_score"] == en["first_score"]
    assert paired["episodes"] == 4 and sum(paired["outcomes"].values()) == 4
    assert "act_s" in paired["shared_first"]
    for arm in (full, none):
        assert arm["summary"]["arm_s"] >= 0 and "shared_first_s" in arm["summary"]
        assert all("shared_first" in e for e in arm["episodes"])
    assert "discordant pair" in capsys.readouterr().out
    # The report reads the per-arm files and skips the paired summary.
    assert main(["report", *map(str, sorted(tmp_path.glob("pair__*.json")))]) == 0
    md = capsys.readouterr().out
    assert "feedback full, paired" in md and "feedback none, paired" in md


def test_paired_needs_an_output_path():
    with pytest.raises(SystemExit, match="--paired needs --out"):
        main(["run", "--agent", "replay", "--paired"])


def test_paired_rejects_feedback(tmp_path):
    with pytest.raises(SystemExit, match="leave out --feedback"):
        main(["run", "--agent", "replay", "--paired", "--feedback", "none",
              "--out", str(tmp_path / "p.json")])


def test_results_keep_code_and_tool_report(tmp_path):
    out = tmp_path / "r.json"
    assert main(["run", "--agent", "replay", "--tasks", "popcount16", "--feedback", "none",
                 "--out", str(out)]) == 0
    traj = json.loads(out.read_text())["episodes"][0]["trajectory"]
    assert "module popcount16" in traj[0]["code"]             # the design that was graded
    assert traj[0]["feedback_shown"] == ""                    # the "none" arm shows nothing
    assert "Hidden tests" in traj[0]["tool_report"]           # but the full report is kept
