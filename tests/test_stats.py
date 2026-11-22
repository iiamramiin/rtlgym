# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Exact intervals and model-specific paired tests in result summaries."""

import json
import math
import runpy
from pathlib import Path

import pytest

from rtlgym import cli
from rtlgym.stats import clopper_pearson, format_ci


@pytest.mark.parametrize(("successes", "total", "expected"), [
    (0, 1, (0, 0.975)),
    (1, 1, (0.025, 1)),
    (0, 10, (0, 0.3084971078187608)),
    (10, 10, (0.6915028921812392, 1)),
    (1, 2, (0.01257911709342506, 0.9874208829065749)),
    (5, 10, (0.18708602844739852, 0.8129139715526015)),
    (50, 100, (0.398321129503301, 0.601678870496699)),
])
def test_clopper_pearson_known_equal_tail_bounds(successes, total, expected):
    assert clopper_pearson(successes, total) == pytest.approx(expected, abs=2e-13)


def test_empty_samples_have_no_interval():
    assert clopper_pearson(0, 0) is None
    assert format_ci(None) == "n/a"


@pytest.mark.parametrize(("successes", "total", "confidence"), [
    (-1, 10, 0.95), (11, 10, 0.95), (0, -1, 0.95), (1.0, 10, 0.95),
    (True, 10, 0.95), (1, 10, 0), (1, 10, 1), (1, 10, float("nan")),
])
def test_invalid_interval_inputs_are_rejected(successes, total, confidence):
    with pytest.raises(ValueError):
        clopper_pearson(successes, total, confidence)


def test_extreme_counts_and_large_samples_stay_numerically_stable():
    lower, upper = clopper_pearson(5000, 10000)
    assert 0.490 < lower < 0.491 and 0.509 < upper < 0.510
    assert lower == pytest.approx(1 - upper, abs=2e-12)
    lower, upper = clopper_pearson(0, 10**12)
    assert lower == 0 and upper == pytest.approx(-math.log(0.025) / 10**12, rel=1e-10)
    assert clopper_pearson(1, 2, 0.99)[0] < clopper_pearson(1, 2, 0.95)[0]


def episode(first=False, solved=False, error=None):
    return {
        "task": "dut", "task_kind": "design", "error": error, "turns": 1,
        "pass@1": first, "pass@1_tests_only": first, "solved": solved,
        "first_score": float(first), "best_score": float(solved), "test_escapes": 0,
        "inconclusive": 0, "return": float(solved),
        "trajectory": [{"score": float(solved), "grade_s": 0.1, "cached": False}],
        "usage": {},
    }


def test_summary_intervals_use_exact_counts_and_include_errors():
    rows = [episode(True, True), episode(False, True), episode(error="no reply")]
    summary = cli.summarize(rows, {})
    assert summary["pass@1_count"] == "1/3" and summary["solved_count"] == "2/3"
    assert summary["pass@1_ci95"] == clopper_pearson(1, 3)
    assert summary["solved_within_turns_ci95"] == clopper_pearson(2, 3)
    assert cli.summarize([], {})["pass@1_ci95"] is None


def test_cli_and_ci_reports_render_each_models_intervals_without_rewriting(tmp_path, capsys):
    names = ("company-a/model", "company-b/model")
    paths = []
    for i, name in enumerate(names):
        rows = [episode(first=bool(i), solved=bool(i)), episode(error="no reply")]
        summary = cli.summarize(rows, {"agent": "ollama", "model": name, "feedback": "full",
                                      "max_turns": 3, "tools": {}, "git_commit": "example"})
        path = tmp_path / f"model-{i}.json"
        path.write_text(json.dumps({"summary": summary, "episodes": rows}))
        paths.append(path)
    before = [path.read_bytes() for path in paths]
    assert cli.main(["report", *map(str, paths)]) == 0
    output = capsys.readouterr().out
    assert "First-attempt 95% CI" in output and "Clopper-Pearson" in output
    for successes in (0, 1):
        assert format_ci(clopper_pearson(successes, 2)) in output
    ci_report = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/ci/summary.py"))["report"]
    output = ci_report(str(tmp_path))
    assert "Pass rate intervals" in output
    for name in names:
        assert f"| {name} | full |" in output
    assert [path.read_bytes() for path in paths] == before


def test_paired_summary_keeps_small_exact_p_values():
    # Sixteen discordant pairs must not become the rounded value zero.
    full = [episode(solved=True) for _ in range(16)]
    none = [episode() for _ in range(16)]
    paired = cli.paired_table({"full": full, "none": none}, ("full", "none"))
    assert paired["mcnemar_exact_p"] == 2 / 2**16
    assert paired["by_kind"]["design"]["mcnemar_exact_p"] == paired["mcnemar_exact_p"]


def test_ci_report_keeps_models_separate_for_exact_mcnemar(tmp_path):
    for name, count in (("company-a", 6), ("company-b", 16)):
        full = [episode(solved=True) for _ in range(count)]
        none = [episode() for _ in range(count)]
        paired = cli.paired_table({"full": full, "none": none}, ("full", "none"))
        paired["mcnemar_exact_p"] = 0.0  # Historical rounded cache; recompute from the counts.
        (tmp_path / f"{name}__paired.json").write_text(json.dumps({
            "meta": {"model": name}, "paired": paired,
        }))
    report = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/ci/summary.py"))["report"]
    output = report(str(tmp_path))
    assert "| company-a | 6 |" in output and str(2 / 2**6) in output
    assert "| company-b | 16 |" in output and str(2 / 2**16) in output
