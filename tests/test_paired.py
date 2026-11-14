"""Paired mode: the arms share the first attempt and nothing else."""
from types import SimpleNamespace

import pytest

import rtlgym.cli as cli
from rtlgym.agents.base import Agent
from rtlgym.task import load_task

pytestmark = pytest.mark.needs_tools


class ChatStub(Agent):
    """Keeps a conversation like the LLM agents do, always answers with the same
    buggy design (so every episode uses all its turns), and records the history it
    had each time it was asked to act."""

    def __init__(self, answer: str, log: list):
        # Kept in a holder: fork() copies list attributes, and the log must be shared.
        self.answer, self.rec = answer, SimpleNamespace(log=log)
        self.messages: list[dict] = []
        self.usage = {"calls": 0}

    def begin_episode(self, obs):
        self.messages = []

    def act(self, obs):
        self.messages.append({"role": "user", "content": obs["feedback"] or obs["spec"]})
        self.rec.log.append((obs["feedback"], [dict(m) for m in self.messages[:-1]]))
        self.messages.append({"role": "assistant", "content": self.answer})
        self.usage["calls"] += 1
        return self.answer


def test_arms_share_only_the_first_attempt(monkeypatch):
    task = load_task("popcount16")
    buggy = (task.root / "candidates" / "bug_width.sv").read_text()
    log: list = []
    monkeypatch.setattr(cli, "make_agent", lambda name, **kw: ChatStub(buggy, log))
    out = cli.run_paired_episode({"max_turns": 3, "use_cache": False}, "stub", {}, "popcount16")

    # One shared first act, then 2 acts per arm (turns 2 and 3).
    assert len(log) == 5
    first_answer = {"role": "assistant", "content": buggy}
    first_user = log[0][1] + [{"role": "user", "content": task.spec}]
    assert log[0][1] == []                                    # the shared first act

    full_acts = [h for fb, h in log[1:] if fb]                # "full" arm sees feedback
    none_acts = [h for fb, h in log[1:] if not fb]            # "none" arm does not
    assert len(full_acts) == 2 and len(none_acts) == 2
    # At its first act, the "none" arm has exactly [first user message, first answer].
    assert none_acts[0] == first_user + [first_answer]
    # Nothing from the "full" arm (its tool feedback) ever reaches the "none" arm.
    for history in none_acts:
        assert all("Hidden tests" not in m["content"] and "Score" not in m["content"]
                   for m in history if m["role"] == "user"), history
    assert out["full"]["turns"] == out["none"]["turns"] == 3
    # Each arm counts only its own calls; the shared first call is reported separately.
    assert out["full"]["usage"]["calls"] == out["none"]["usage"]["calls"] == 2
    assert out["full"]["shared_first"]["usage"]["calls"] == 1
