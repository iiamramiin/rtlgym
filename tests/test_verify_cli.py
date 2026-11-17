# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Check verification task selection, baseline routing and outcome reports."""

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from rtlgym import cli
from rtlgym.agents.base import first_prompt
from rtlgym.agents.replay import ReplayAgent
from rtlgym.task import load_task


@pytest.fixture
def verification_tasks(tmp_path):
    parent = tmp_path / "dut"
    parent.mkdir()
    (parent / "task.toml").write_text('id="dut"\ntop="dut"\n[formal]\ndepth=1\n')
    (parent / "ref.sv").write_text("module dut(input x, output y); assign y=x; endmodule\n")
    (parent / "spec.md").write_text("Output y equals input x.")
    (parent / "test_dut.py").write_text("")
    task = tmp_path / "verify_dut"
    (task / "candidates").mkdir(parents=True)
    (task / "task.toml").write_text(
        'id="verify_dut"\nkind="verify"\nparent="dut"\n'
        '[verification]\ndepth=1\nmanifest="mutants.json"\n'
    )
    (task / "spec.md").write_text("Write rtl_checker. Check y equals x.")
    (task / "ref.sv").write_text("module rtl_checker(input x,y); always @* assert(y==x); endmodule\n")
    (task / "candidates" / "bug_empty.sv").write_text("module rtl_checker(input x,y); endmodule\n")
    (task / "mutants.json").write_text('{"mutants": []}')
    return tmp_path


def test_verify_loader_keeps_checker_and_dut_sources_distinct(verification_tasks):
    task = load_task("verify_dut", verification_tasks)
    assert task.kind == "verify" and task.top == "rtl_checker" and task.dut_top == "dut"
    assert task.ref_path == verification_tasks / "verify_dut" / "ref.sv"
    assert task.dut_ref_path == verification_tasks / "dut" / "ref.sv"
    assert task.candidates_dir.parent == task.verification_root
    assert cli._tasks_arg("verify", verification_tasks) == ["verify_dut"]
    assert cli._tasks_arg("design", verification_tasks) == ["dut"]
    before = task.fingerprint()
    (task.root / "mutants.json").write_text('{"mutants": ["changed"]}')
    assert task.fingerprint() != before


def test_verify_replay_uses_the_checker_bundle(verification_tasks):
    task = load_task("verify_dut", verification_tasks)
    agent = ReplayAgent(verification_tasks)
    obs = {"task_id": task.id, "task_kind": "verify", "top": task.top, "spec": task.spec}
    agent.begin_episode(obs)
    assert "assert(y==x)" in agent.act(obs)
    assert "verification assertions" in first_prompt(obs)


def test_verify_baselines_never_grade_dut_sources(verification_tasks, monkeypatch, capsys):
    task = load_task("verify_dut", verification_tasks)
    seen = []
    verification = {"status": "pass", "caught": 2, "mutants_total": 2,
                    "assertions": 3, "state_bits": 8, "checker_bytes": 123}

    def evaluate(selected, source, **_kwargs):
        seen.append((selected.kind, source))
        return SimpleNamespace(
            score=1.0, tests_passed=2, tests_total=2, formal_status="pass", formal_message="",
            frontend_errors=[], resource_failures={}, ppa_unavailable=None, sim_frontend=None,
            synth_frontend=None, formal_frontend=None, timings_s={}, compile_ok=True, lint_warnings=[],
            cells=None, ref_cells=None, depth=None, violations=[], breakdown={}, accepted=True,
            verification=verification,
        )

    monkeypatch.setattr(cli, "evaluate", evaluate)
    monkeypatch.setattr(cli, "tool_versions", lambda: {})
    assert cli.main(["--tasks-root", str(verification_tasks), "baselines", "--tasks", "verify"]) == 0
    assert len(seen) == 2 and all(kind == "verify" and "rtl_checker" in code for kind, code in seen)
    assert ("verify", task.ref_path.read_text()) in seen
    output = capsys.readouterr().out
    assert "checker pass, caught 2/2 mutants, 3 assertions, 8 state bits, 123 bytes" in output


def test_verify_cannot_disable_formal_grading(verification_tasks):
    with pytest.raises(SystemExit, match="require their formal"):
        cli.main(["--tasks-root", str(verification_tasks), "baselines", "--tasks", "verify", "--no-formal"])


def episode(status, caught, total, weighted, score, **extra):
    details = {"status": status, "caught": caught, "mutants_total": total,
               "weighted_caught": weighted, "families": {"logic": {"caught": caught, "total": total}}}
    return {
        "task": "verify_dut", "task_kind": "verify", "error": None, "pass@1": score == 1,
        "solved": score == 1, "pass@1_tests_only": score == 1, "turns": 1,
        "test_escapes": 0, "inconclusive": int(status == "inconclusive"), "first_score": score,
        "best_score": score, "verification": details, "usage": {},
        "trajectory": [{"score": score, "grade_s": 0.1, "cached": False,
                        "verification": details, "solved": score == 1}],
        **extra,
    }


def test_verify_summary_uses_final_checker_and_keeps_false_alarms_visible():
    rows = [episode("pass", 2, 4, 0.5, 0.5), episode("false_alarm", 0, 4, 0, 0),
            episode("invalid", 0, 0, 0, 0)]
    rows[0]["verification"].update(assertions=6, state_bits=12, checker_bytes=300)
    rows[1]["verification"].update(assertions=3, state_bits=0, checker_bytes=150)
    summary = cli.summarize(rows, {})
    counts = summary["by_kind"]["verify"]["verification"]
    assert counts["episodes"] == counts["graded_episodes"] == 3
    assert counts["caught"] == 2 and counts["mutants_total"] == 8
    assert counts["false_alarm_episodes"] == counts["invalid_episodes"] == 1
    assert counts["mutation_rate"] == 0.25 and counts["mean_score"] == 0.1667
    assert counts["families"]["logic"] == {"caught": 2, "total": 8}
    assert (counts["mean_assertions"], counts["mean_state_bits"], counts["mean_checker_bytes"]) == (3, 4, 150)


def test_verify_report_and_ci_summary_retain_only_aggregate_metrics(tmp_path, capsys):
    row = episode("pass", 2, 4, 0.5, 0.5)
    row["verification"]["targets"] = [{"name": "private_mutant_identity", "status": "caught"}]
    meta = {"agent": "replay", "feedback": "full", "max_turns": 1, "git_commit": "example",
            "tools": {}, "formal": True}
    summary = cli.summarize([row], meta)
    out = tmp_path / "result.json"
    out.write_text(json.dumps({"summary": summary, "episodes": [row]}))
    assert cli.main(["report", str(out)]) == 0
    report = capsys.readouterr().out
    assert "Verification checker results" in report and "2/4" in report
    assert "private_mutant_identity" not in report
    ci_report = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "ci" / "summary.py"))
    report = ci_report["report"](str(tmp_path))
    assert "Verification checker results" in report and "2/4" in report
    assert "private_mutant_identity" not in report
