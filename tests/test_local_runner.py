# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Local script orchestration without starting a model or accessing the network."""

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "local" / "run_eval.sh"
REPORT = runpy.run_path(str(ROOT / "scripts" / "local" / "make_table.py"))


def _executable(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def runner(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    calls = tmp_path / "calls.jsonl"
    python = tmp_path / "venv" / "bin" / "python"
    _executable(python, f"""#!{sys.executable}
import json
import os
import sys
if len(sys.argv) > 2 and sys.argv[1:3] == ["-m", "rtlgym"]:
    with open(os.environ["RECORDED_CALLS"], "a") as out:
        out.write(json.dumps(sys.argv[3:]) + "\\n")
    if sys.argv[3] == "list":
        print("popcount16 easy")
        print("fifo_sync medium")
    sys.exit(0)
if len(sys.argv) > 1 and sys.argv[1].endswith("make_table.py"):
    with open(os.environ["RECORDED_CALLS"], "a") as out:
        out.write(json.dumps(sys.argv[1:]) + "\\n")
    sys.exit(0)
os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
""")
    _executable(binaries / "curl", '#!/bin/sh\nprintf "%s\\n" "$MODEL_TAGS"\n')
    tags = {"models": [
        {"name": "llama3.1:8b", "size": 4 * 2**30},
        {"name": "qwen3:14b", "size": 9 * 2**30},
        {"name": "qwen3:30b-a3b", "size": 18 * 2**30},
    ]}
    environment = {
        **os.environ, "REPO_SRC": str(repo), "RTLGYM_DIR": str(repo),
        "VENV": str(python.parents[1]), "OUT": str(tmp_path / "out"),
        "OLLAMA_URL": "http://localhost:11434", "RAM_GB": "15.435",
        "MODEL_TAGS": json.dumps(tags), "RECORDED_CALLS": str(calls),
        "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
        "MODELS": "llama3.1:8b qwen3:14b qwen3:30b-a3b",
        "TURNS": "3", "SAMPLES": "1", "PAIRED": "1", "TASKS": "all",
        "THINK": "off", "SEED": "123", "NUM_CTX": "12288", "MAX_TOKENS": "2048",
    }

    def run(mode, **overrides):
        result = subprocess.run(["bash", str(SCRIPT), mode], env={**environment, **overrides},
                                capture_output=True, text=True, timeout=30)
        recorded = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
        return result, recorded

    return run, repo, tmp_path


def test_smoke_is_two_tasks_one_sample_paired_and_filters_explicit_large_models(runner):
    run, _, _ = runner
    result, calls = run("smoke", SAMPLES="99", PAIRED="0")
    assert result.returncode == 0, result.stdout + result.stderr
    runs = [call for call in calls if call[0] == "run"]
    assert len(runs) == 2
    for call in runs:
        assert call[call.index("--tasks") + 1] == "popcount16,verify_popcount16"
        assert call[call.index("--samples") + 1] == "1" and "--paired" in call
        assert call[call.index("--max-turns") + 1] == "3"
        assert call[call.index("--think") + 1] == "off"
        assert call[call.index("--seed") + 1] == "123"
        assert call[call.index("--num-ctx") + 1] == "12288"
        assert call[call.index("--max-tokens") + 1] == "2048"
    assert "Skipping qwen3:30b-a3b" in result.stdout


def test_selected_tasks_reach_all_mode_without_expanding_to_every_kind(runner):
    run, _, _ = runner
    result, calls = run("all", TASKS="fifo_sync,noc_router5", MODELS="llama3.1:8b")
    assert result.returncode == 0, result.stdout + result.stderr
    call = next(call for call in calls if call[0] == "run")
    assert call[call.index("--tasks") + 1] == "fifo_sync,noc_router5"
    assert "--paired" in call


def test_probe_uses_selected_probe_and_run_task_counts(runner):
    run, _, _ = runner
    result, calls = run("probe", PROBE_TASKS="fifo_sync", PROBE_TURNS="1",
                        TASKS="fifo_sync,noc_router5", MODELS="llama3.1:8b")
    assert result.returncode == 0, result.stdout + result.stderr
    call = next(call for call in calls if call[0] == "run")
    assert call[call.index("--tasks") + 1] == "fifo_sync"
    assert call[call.index("--max-turns") + 1] == "1"
    estimate = next(call for call in calls if call[0].endswith("make_table.py"))
    assert estimate[-5:] == ["2", "2", "1", "3", "1"]


def test_partial_paired_output_does_not_skip_the_model(runner):
    run, _, tmp_path = runner
    output = tmp_path / "out"
    output.mkdir()
    (output / "llama3.1_8b__paired.json").write_text("{}")
    result, calls = run("smoke", MODELS="llama3.1:8b")
    assert result.returncode == 0, result.stdout + result.stderr
    assert any(call[0] == "run" for call in calls)


def test_sync_copies_tracked_archives_without_deleting_existing_results(runner):
    run, source, tmp_path = runner
    archive = source / "results" / "claude" / "fixture.json"
    archive.parent.mkdir(parents=True)
    archive.write_text('{"source":"fixture"}')
    ignored = source / "results" / "local" / "scratch.json"
    ignored.parent.mkdir()
    ignored.write_text("{}")
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "results/claude/fixture.json"], check=True)
    destination = tmp_path / "linux"
    existing = destination / "results" / "custom" / "kept.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("kept")
    result, _ = run("probe", RTLGYM_DIR=str(destination), MODELS="llama3.1:8b")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (destination / "results" / "claude" / "fixture.json").read_bytes() == archive.read_bytes()
    assert existing.read_text() == "kept"
    assert not (destination / "results" / "local" / "scratch.json").exists()


def test_local_table_keeps_exact_counts_truncations_and_per_model_pvalues(tmp_path, capsys):
    summary = {
        "model": "local", "feedback": "full", "episodes": 20, "errors": 0,
        "pass@1_count": "0/20", "solved_count": "20/20", "pass@1": 0.0,
        "solved_within_turns": 1.0, "mean_best_score": 1.0, "test_escape_attempts": 0,
        "max_turns": 3, "truncated_attempts": 1, "paired": True,
        "usage": {"calls": 20, "generate_s": 200.0},
        "per_task": {"fifo_sync": {"pass@1_count": "0/20", "solved_count": "20/20",
                                    "truncated_attempts": 1}},
    }
    (tmp_path / "local__full.json").write_text(json.dumps({"summary": summary}))
    (tmp_path / "local__none.json").write_text(json.dumps({
        "summary": {**summary, "feedback": "none", "solved_count": "0/20",
                    "solved_within_turns": 0.0, "mean_best_score": 0.0,
                    "per_task": {"fifo_sync": {"pass@1_count": "0/20", "solved_count": "0/20"}},
                    "usage": {"calls": 40, "generate_s": 400.0}}}))
    (tmp_path / "local__paired.json").write_text(json.dumps({
        "meta": {"model": "local"}, "paired": {
            "arms": ["full", "none"], "episodes": 20,
            "outcomes": {"both": 0, "only_full": 20, "only_none": 0, "neither": 0, "errored": 0},
            "informative_episodes": 20, "discordant_pairs": 20, "mcnemar_exact_p": 0.0,
            "shared_first": {"calls": 20, "generate_s": 200.0},
        }}))
    REPORT["table"](str(tmp_path))
    output = capsys.readouterr().out
    assert "First attempt (95% CI)" in output and "Clopper–Pearson" in output
    assert "0/20 [" in output and "20/20 [" in output
    assert "0/20 → 20/20; 1 truncated" in output
    assert "1.90735e-06" in output  # exact paired test, not the rounded archived zero
    assert "| local | 80 | 10.00 |" in output  # shared first calls counted once


def test_local_table_does_not_reconstruct_exact_counts_from_rounded_rates(tmp_path, capsys):
    summary = {"model": "old", "feedback": "full", "episodes": 3001, "errors": 0,
               "pass@1": 0.1, "solved_within_turns": 0.2, "mean_best_score": 0.3,
               "test_escape_attempts": 0, "max_turns": 3}
    (tmp_path / "old.json").write_text(json.dumps({"summary": summary}))
    REPORT["table"](str(tmp_path))
    assert "| old | full | 3001 (0) | n/a | n/a |" in capsys.readouterr().out


def test_local_estimate_counts_shared_first_attempt_once():
    assert REPORT["call_budget"](12, 5, 3, True) == 300
    assert REPORT["call_budget"](12, 5, 3, False) == 360
    assert REPORT["call_budget"](2, 1, 1, True) == 2


def test_windows_launcher_carries_settings_and_converts_only_windows_output_paths():
    source = (ROOT / "scripts" / "local" / "run_all.ps1").read_text(encoding="utf-8")
    settings = source.split("$SettingNames =", 1)[1].split("# An elevated", 1)[0]
    assert all(f'"{name}"' in settings for name in ("NUM_CTX", "TASKS", "OUT", "RUN_MODE"))
    # OUT must not travel in the raw environment passthrough list.
    assert '$_ -notin @("RTLGYM_WSL_DIR", "OUT", "RUN_MODE")' in source
    assert '$pass += "OUT=$(ConvertTo-WslPath $env:OUT)"' in source
    converter = source.split("function ConvertTo-WslPath", 1)[1].split("function Test-NeedsRestart", 1)[0]
    assert 'if ($p.StartsWith("/")) { return $p }' in converter
    assert 'throw "Use an absolute Windows or Linux path."' in converter
    assert 'if (-not $runMode) { $runMode = "probe" }' in source
