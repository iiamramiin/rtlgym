# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Repair prompts, starter guards and paired trajectories."""

import json

import pytest

from rtlgym import RTLEnv, load_task
from rtlgym.agents.base import first_prompt
from rtlgym.checks import repair_source, same_repair_source
from rtlgym.cli import main
from rtlgym.env import _lines_changed


def test_repair_source_hides_comments_and_keeps_quoted_text():
    source = '// explanation\nmodule m; string s = "// value"; /* explanation */ endmodule\n'
    clean = repair_source(source)
    assert "explanation" not in clean
    assert '"// value"' in clean
    assert same_repair_source(source, "  " + clean)
    assert not same_repair_source(source, clean.replace("value", "changed"))


def test_line_edits_count_insertions_deletions_and_replacements():
    assert _lines_changed("a\nb\nc\n", "a\nx\nc\nnew\n") == 2
    assert _lines_changed("a\nb\nc\n", "a\nc\n") == 1
    assert _lines_changed("a\nb\nc\n", "a // comment\nb\nc\n") == 0


@pytest.mark.needs_tools
def test_starter_guard_without_formal():
    task = load_task("repair_secded_ecc")
    env = RTLEnv(feedback="none", use_formal=False)
    obs, _ = env.reset(task.id)
    assert obs["feedback"] == "" and "Formal checking is disabled." in obs["starter_feedback"]
    assert obs["spec"] == task.spec and "/*" not in obs["starter_code"] and "//" not in obs["starter_code"]
    assert obs["turn"] == 0
    prompts = first_prompt(obs)
    assert all(part in prompts for part in (obs["spec"], obs["starter_code"], obs["starter_feedback"]))
    obs, reward, done, _, info = env.step(task.start_code)
    assert reward == 0 and not done and not info["solved"]
    assert info["eval"].all_tests_pass and info["eval"].unchanged_starter
    assert info["lines_changed"] == 0
    assert obs["feedback"] == "" and "starter_feedback" not in obs


@pytest.mark.needs_tools
def test_paired_mixed_run_shares_starter_and_first_grade(tmp_path, monkeypatch):
    import rtlgym.env as env_module

    evaluated = []
    original = env_module.evaluate

    def record(task, code, *args, **kwargs):
        evaluated.append((task.id, code))
        return original(task, code, *args, **kwargs)

    monkeypatch.setattr(env_module, "evaluate", record)
    out = tmp_path / "mixed.json"
    assert main(["run", "--tasks", "repair_popcount16,popcount16", "--paired", "--no-cache",
                 "--workers", "1", "--out", str(out)]) == 0
    repair_evals = [code for tid, code in evaluated if tid == "repair_popcount16"]
    # Initial stimulus, shared first action, and each arm's second action.
    assert len(repair_evals) == 4
    assert sum(tid == "popcount16" for tid, _ in evaluated) == 4
    full, none, paired = [json.loads((tmp_path / f"mixed__{name}.json").read_text())
                          for name in ("full", "none", "paired")]
    assert paired["paired"]["by_kind"]["repair"]["episodes"] == 1
    assert {row["task_kind"] for row in paired["paired"]["rows"]} == {"repair", "design"}
    for results in (full, none):
        assert set(results["summary"]["by_kind"]) == {"repair", "design"}
        repair, design = results["episodes"]
        assert repair["task_kind"] == "repair" and design["task_kind"] == "design"
        assert not repair["pass@1"] and repair["solved"] and repair["turns"] == 2
        assert repair["trajectory"][0]["reward"] == 0 and repair["trajectory"][0]["lines_changed"] == 0
        assert repair["trajectory"][1]["lines_changed"] > 0
        assert "lines_changed" not in design["trajectory"][0]
    a, b = [results["episodes"][0]["trajectory"][0] for results in (full, none)]
    assert "Hidden tests" in a["feedback_shown"] and b["feedback_shown"] == ""
    assert a["code"] == b["code"] and a["grade_s"] == b["grade_s"]
