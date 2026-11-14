"""Result accounting: every episode counts, including ones that errored."""
from rtlgym.cli import paired_table, summarize


def ep(task, solved=False, first=False, best=0.0, error=None, turns=1, usage=None):
    traj = [{"grade_s": 0.1, "cached": False, "test_escape": False}] * turns
    return {"task": task, "error": error, "turns": turns, "pass@1": first,
            "pass@1_tests_only": first, "solved": solved, "test_escapes": 0, "inconclusive": 0,
            "first_score": best if first else 0.1 * turns, "best_score": best, "return": best,
            "trajectory": traj, "usage": usage}


def test_errored_episodes_count_as_unsolved():
    results = [
        ep("a", solved=True, first=True, best=0.97),
        ep("a", best=0.4, turns=2),
        ep("b", error="RuntimeError: no reply from Ollama within 1800 s", turns=0),
        ep("b", error="RuntimeError: timeout on turn 2", best=0.3, turns=1),  # mid-episode
    ]
    s = summarize(results, {})
    assert s["episodes"] == 4 and s["errors"] == 2
    assert s["pass@1"] == 0.25 and s["pass@1_count"] == "1/4"   # not 1/2
    assert s["solved_within_turns"] == 0.25 and s["solved_count"] == "1/4"
    # Errored episodes keep what they reached before the error (0 if nothing graded).
    assert abs(s["mean_best_score"] - (0.97 + 0.4 + 0.0 + 0.3) / 4) < 1e-3
    assert s["per_task"]["b"] == {"episodes": 2, "errors": 2, "pass@1": 0.0, "solved": 0.0,
                                  "pass@1_count": "0/2", "solved_count": "0/2",
                                  "mean_turns": 0.5}


def test_usage_includes_errored_episodes():
    results = [ep("a", usage={"calls": 2, "generate_s": 1.5}),
               ep("a", error="boom", usage={"calls": 1, "generate_s": 0.25})]
    assert summarize(results, {})["usage"] == {"calls": 3, "generate_s": 1.75}


def test_all_errors_still_summarize():
    s = summarize([ep("a", error="x", turns=0)], {})
    assert s["pass@1"] == 0.0 and s["errors"] == 1 and s["solved_count"] == "0/1"


def test_paired_table_counts_discordant_pairs():
    full = [ep("a", solved=True), ep("b", solved=True), ep("c"), ep("d", solved=True)]
    none = [ep("a", solved=True), ep("b"), ep("c", solved=True), ep("d")]
    t = paired_table({"full": full, "none": none}, ("full", "none"))
    assert t["outcomes"] == {"both": 1, "only_full": 2, "only_none": 1, "neither": 0}
    assert t["discordant_pairs"] == 3 and [r["outcome"] for r in t["rows"]] == [
        "both", "only_full", "only_none", "only_full"]


def test_git_commit_marks_uncommitted_changes(tmp_path, monkeypatch):
    import subprocess

    from rtlgym.cli import _git_commit
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    git("init", "-q")
    git("-c", "user.email=a@b", "-c", "user.name=n", "commit", "-q", "--allow-empty", "-m", "x")
    (tmp_path / "f.txt").write_text("1")
    git("add", "f.txt")
    git("-c", "user.email=a@b", "-c", "user.name=n", "commit", "-q", "-m", "y")
    clean = _git_commit(tmp_path)
    assert len(clean) == 40 and not clean.endswith("-dirty")
    (tmp_path / "f.txt").write_text("2")
    assert _git_commit(tmp_path) == clean + "-dirty"
    (tmp_path / "untracked.txt").write_text("results are not code")
    (tmp_path / "f.txt").write_text("1")
    assert _git_commit(tmp_path) == clean           # untracked files do not count
    assert _git_commit(tmp_path / "nope") == "unknown"
