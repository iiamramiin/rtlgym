# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Output-limit reporting is independent of grading and feedback arms."""

import copy
import json

import pytest

from rtlgym import cli
from rtlgym.agents.base import Agent
from rtlgym.evaluator import EvalResult


class ReplyAgent(Agent):
    def __init__(self, replies):
        self.replies = list(replies)
        self.index = 0
        self.usage = {"calls": 0, "truncated": 0, "output_tokens": 0}

    def act(self, obs):
        reply, cut_off = self.replies[self.index]
        self.index += 1
        self.usage["calls"] += 1
        self.usage["truncated"] += int(cut_off)
        self.usage["output_tokens"] += 32000 if cut_off else 10
        return reply


@pytest.fixture
def rejected_grader(monkeypatch):
    graded = []

    def evaluate(task, code, *args, **kwargs):
        result = EvalResult(task.id, "example", violations=["incomplete source"])
        if task.kind == "verify":
            result.verification = {"status": "invalid", "caught": 0, "mutants_total": 0,
                                   "weighted_caught": 0.0, "families": {}}
        graded.append((code, copy.deepcopy(result.to_dict())))
        return result

    monkeypatch.setattr("rtlgym.env.evaluate", evaluate)
    return graded


def run(monkeypatch, task, replies, *, paired=False):
    monkeypatch.setattr(cli, "make_agent", lambda *_args, **_kwargs: ReplyAgent(replies))
    fn = cli.run_paired_episode if paired else cli.run_episode
    return fn({"max_turns": len(replies), "use_cache": False}, "stub", {}, task)


@pytest.mark.parametrize("task", ["popcount16", "repair_popcount16", "verify_popcount16"])
def test_cut_off_incomplete_attempt_is_reported_without_changing_grade(task, monkeypatch, rejected_grader):
    row = run(monkeypatch, task, [("```systemverilog\nmodule incomplete(", True)])
    turn = row["trajectory"][0]
    assert turn["report_status"] == row["report_status"] == "truncated"
    assert turn["usage"]["truncated"] == row["truncated_attempts"] == 1
    assert turn["complete_code"] is False
    assert turn["score"] == turn["reward"] == row["return"] == 0
    assert not turn["solved"] and not row["solved"]
    assert rejected_grader[-1][1]["score"] == 0
    if task.startswith("verify"):
        # The original grader verdict remains available, separate from reporting.
        assert turn["verification"]["status"] == row["verification"]["status"] == "invalid"
        assert rejected_grader[-1][1]["verification"] == turn["verification"]
    summary = cli.summarize([row], {})
    assert summary["truncated_attempts"] == summary["per_task"][task]["truncated_attempts"] == 1
    if task.startswith("verify"):
        counts = summary["by_kind"]["verify"]["verification"]
        assert counts["truncated_episodes"] == 1
        assert counts["invalid_episodes"] == counts["graded_episodes"] == 0


@pytest.mark.parametrize("reply", [
    "```systemverilog\nmodule dut; endmodule\n```\nexplanation cut off",
    "```systemverilog\nmodule incomplete(\n```\nexplanation cut off",
    "module dut; endmodule",
    "```systemverilog\nmodule dut; endmodule",
    "module wrong_name; endmodule",
])
def test_extracted_complete_block_is_not_relabelled(reply, monkeypatch, rejected_grader):
    row = run(monkeypatch, "popcount16", [(reply, True)])
    assert row["truncated_attempts"] == 0 and "report_status" not in row
    assert row["trajectory"][0]["complete_code"] is True
    assert "report_status" not in row["trajectory"][0]


@pytest.mark.parametrize("reply", [
    "module dut; // endmodule",
    'module dut; localparam MESSAGE="endmodule";',
    "module dut; /* endmodule */",
])
def test_comments_or_quotes_do_not_supply_module_end(reply):
    assert cli._complete_code(reply, reply) is False


def test_nontruncated_invalid_and_cumulative_usage_do_not_become_truncated(monkeypatch, rejected_grader):
    row = run(monkeypatch, "verify_popcount16", [("incomplete", True), ("still incomplete", False)])
    first, second = row["trajectory"]
    assert first["report_status"] == "truncated" and first["usage"]["truncated"] == 1
    assert "report_status" not in second and second["usage"]["truncated"] == 0
    assert row["truncated_attempts"] == 1 and "report_status" not in row
    counts = cli.summarize([row], {})["by_kind"]["verify"]["verification"]
    assert counts["invalid_episodes"] == 1 and counts["truncated_episodes"] == 0


@pytest.mark.parametrize("task", ["popcount16", "repair_popcount16", "verify_popcount16"])
def test_paired_first_attempt_keeps_shared_usage_without_leaking_to_retries(
        task, monkeypatch, rejected_grader):
    rows = run(monkeypatch, task, [("incomplete", True), ("incomplete", False)], paired=True)
    for row in rows.values():
        assert row["shared_first"]["usage"]["truncated"] == 1
        assert row["usage"]["calls"] == 1 and row["usage"]["truncated"] == 0
        first, retry = row["trajectory"]
        assert first["report_status"] == "truncated" and first["usage"]["truncated"] == 1
        assert retry["usage"]["truncated"] == 0 and "report_status" not in retry
        assert row["truncated_attempts"] == 1


def test_historical_one_turn_report_is_refreshed_only_in_memory(
        monkeypatch, rejected_grader, tmp_path, capsys):
    row = run(monkeypatch, "verify_popcount16", [("```systemverilog\nmodule rtl_checker(", True)])
    row.pop("report_status")
    row.pop("truncated_attempts")
    for key in ("report_status", "usage", "complete_code"):
        row["trajectory"][0].pop(key)
    meta = {"agent": "stub", "max_turns": 1, "git_commit": "example", "tools": {}}
    original = {"summary": cli.summarize([row], meta), "episodes": [row]}
    before = copy.deepcopy(original)
    path = tmp_path / "run.json"
    path.write_text(json.dumps(original))
    raw = path.read_bytes()
    refreshed = cli.refresh_report(original)
    assert original == before and path.read_bytes() == raw
    assert refreshed["episodes"][0]["report_status"] == "truncated"
    assert refreshed["summary"]["truncated_attempts"] == 1
    assert cli.main(["report", str(path)]) == 0
    report = capsys.readouterr().out
    assert "Truncated" in report and "; 1 truncated" in report
    assert path.read_bytes() == raw


def test_historical_multiple_turns_do_not_guess_where_a_cutoff_occurred(monkeypatch, rejected_grader):
    row = run(monkeypatch, "popcount16", [("incomplete", True), ("incomplete", False)])
    row.pop("truncated_attempts")
    for turn in row["trajectory"]:
        for key in ("usage", "complete_code", "report_status"):
            turn.pop(key, None)
    refreshed = cli.refresh_report({"episodes": [row]})
    assert refreshed["episodes"][0]["truncated_attempts"] == 0
    assert all("report_status" not in turn for turn in refreshed["episodes"][0]["trajectory"])


def test_unrelated_closed_fence_does_not_hide_cut_off_rtl(monkeypatch, rejected_grader):
    reply = "```text\nplan\n```\n```systemverilog\nmodule incomplete("
    row = run(monkeypatch, "popcount16", [(reply, True)])
    assert row["trajectory"][0]["code"].strip() == "module incomplete("
    assert row["report_status"] == "truncated"


def test_unclosed_complete_module_follows_the_actual_task_extractor(monkeypatch, rejected_grader):
    reply = "```systemverilog\nmodule rtl_checker; endmodule"
    design = run(monkeypatch, "popcount16", [(reply, True)])
    checker = run(monkeypatch, "verify_popcount16", [(reply, True)])
    assert design["trajectory"][0]["code"].strip() == "module rtl_checker; endmodule"
    assert design["trajectory"][0]["complete_code"] is True
    assert "report_status" not in design
    assert checker["trajectory"][0]["code"].startswith("```systemverilog")
    assert checker["trajectory"][0]["complete_code"] is False
    assert checker["report_status"] == "truncated"
