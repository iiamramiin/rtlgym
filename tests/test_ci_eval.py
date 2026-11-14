"""scripts/ci/eval.sh and summary.py, run locally with the replay agent (no API)."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "eval.sh"
spec = importlib.util.spec_from_file_location("ci_summary", ROOT / "scripts" / "ci" / "summary.py")
ci_summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci_summary)


def test_plan_counts_the_most_calls():
    # Paired: 1 shared first attempt + 2 arms x (turns - 1).
    assert ci_summary.plan(1, 8, 5, 3, paired=True, arms=2) == 8 * 5 * 5
    assert ci_summary.plan(2, 2, 1, 3, paired=True, arms=2) == 2 * 2 * 5
    # Unpaired: every arm can use every turn.
    assert ci_summary.plan(1, 8, 5, 3, paired=False, arms=2) == 8 * 5 * 6


def _arm(model, fb, usage, inconclusive=0, errors=0):
    return {"summary": {"model": model, "agent": "claude", "feedback": fb, "usage": usage,
                        "inconclusive_attempts": inconclusive, "errors": errors}}


def test_report_totals_include_shared_first_calls(tmp_path):
    u = {"calls": 3, "input_tokens": 1000, "output_tokens": 5000}
    (tmp_path / "m__full.json").write_text(json.dumps(_arm("m", "full", u)))
    (tmp_path / "m__none.json").write_text(json.dumps(_arm("m", "none", u, inconclusive=2)))
    (tmp_path / "m__paired.json").write_text(json.dumps({
        "meta": {"model": "m"},
        "paired": {"episodes": 4, "informative_episodes": 3, "discordant_pairs": 2,
                   "mcnemar_exact_p": 0.5,
                   "outcomes": {"both": 1, "only_full": 2, "only_none": 0, "neither": 1,
                                "errored": 0},
                   "shared_first": {"act_s": 9.0, "calls": 4, "input_tokens": 400,
                                    "output_tokens": 800}}}))
    md = ci_summary.report(str(tmp_path))
    assert "| m | 10 | 2,400 | 10,800 |" in md               # 3 + 3 + 4 shared calls
    assert md.startswith("**WARNING:** **Inconclusive attempts: 2**")
    assert "m, feedback none: 2 inconclusive, 0 errored" in md
    assert "| m | 4 | 1 | 2 | 0 | 1 | 0 | 3 | 2 | 0.5 |" in md


def _run(tmp_path, **env):
    out = tmp_path / "results"
    step = tmp_path / "step.md"
    e = {**os.environ, "AGENT": "replay", "PYTHON": sys.executable, "OUT": str(out),
         "GITHUB_STEP_SUMMARY": str(step), **env}
    r = subprocess.run(["bash", str(SCRIPT)], env=e, cwd=ROOT, capture_output=True, text=True,
                       timeout=300)
    return r, out, step


@pytest.mark.needs_tools
@pytest.mark.parametrize("paired", ["true", "false"])
def test_eval_script_with_the_replay_agent(tmp_path, paired):
    r, out, step = _run(tmp_path, TASKS="popcount16", SAMPLES="1", PAIRED=paired)
    assert r.returncode == 0, r.stdout + r.stderr
    expected = {"replay__full.json", "replay__none.json", "summary.md"}
    if paired == "true":
        expected.add("replay__paired.json")
    assert {p.name for p in out.iterdir()} == expected
    calls = 5 if paired == "true" else 6
    assert f"at most {calls} API calls" in r.stdout
    md = step.read_text()
    assert md == (out / "summary.md").read_text()
    assert "| replay (feedback full" in md and "Inconclusive attempts: 0" in md
    assert "### Tokens per model" in md
    assert ("### Paired outcomes" in md) == (paired == "true")


@pytest.mark.needs_tools
def test_eval_script_reports_a_failed_run(tmp_path):
    r, out, step = _run(tmp_path, TASKS="no_such_task", SAMPLES="1")
    assert r.returncode == 1
    assert "No result files were written." in step.read_text()
