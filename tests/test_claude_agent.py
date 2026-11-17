"""The Claude agent is tested with a fake client, so no API key or network is needed."""
import hashlib
from types import SimpleNamespace

import pytest

from rtlgym.agents.claude import SYSTEM_PROMPT, VERIFY_SYSTEM_PROMPT, ClaudeAgent


def block(kind, text=""):
    return SimpleNamespace(type=kind, text=text) if kind == "text" else SimpleNamespace(
        type=kind, thinking="...", signature="sig")


class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.msg


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        content, stop = self.replies.pop(0)
        return FakeStream(SimpleNamespace(content=content, stop_reason=stop,
                                          usage=SimpleNamespace(input_tokens=10,
                                                                output_tokens=5)))


def make(replies, **kw):
    fake = FakeMessages(replies)
    return ClaudeAgent(client=SimpleNamespace(messages=fake), **kw), fake


def test_conversation_carries_feedback_and_thinking_blocks():
    agent, fake = make([
        ([block("thinking"), block("text", "```verilog\nmodule a; endmodule\n```")], "end_turn"),
        ([block("text", "```verilog\nmodule b; endmodule\n```")], "end_turn"),
    ], model="test-model")
    obs = {"top": "a", "spec": "SPEC", "feedback": "", "turns_left": 3}
    agent.begin_episode(obs)
    assert "module a" in agent.act(obs)
    obs2 = dict(obs, feedback="Hidden tests: 1/3 passed", turns_left=2)
    assert "module b" in agent.act(obs2)
    second = fake.calls[1]
    assert second["model"] == "test-model"
    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    # The assistant turn is passed back unchanged, thinking block included.
    assert [b.type for b in second["messages"][1]["content"]] == ["thinking", "text"]
    assert "Hidden tests: 1/3 passed" in second["messages"][-1]["content"]
    assert agent.usage["calls"] == 2 and agent.usage["input_tokens"] == 20


def test_no_sampling_parameters_and_optional_effort():
    agent, fake = make([([block("text", "x")], "end_turn")], effort="medium")
    agent.act({"top": "a", "spec": "S", "feedback": "", "turns_left": 1})
    call = fake.calls[0]
    assert "temperature" not in call and "top_p" not in call and "top_k" not in call
    assert call["output_config"] == {"effort": "medium"}
    assert call["max_tokens"] >= 16000

    agent2, fake2 = make([([block("text", "x")], "end_turn")])
    agent2.act({"top": "a", "spec": "S", "feedback": "", "turns_left": 1})
    assert "output_config" not in fake2.calls[0]


def test_refusal_and_truncation_are_counted():
    agent, _ = make([([], "refusal"), ([block("text", "partial")], "max_tokens")])
    obs = {"top": "a", "spec": "S", "feedback": "", "turns_left": 2}
    assert agent.act(obs) == ""
    agent.act(dict(obs, feedback="Rejected", turns_left=1))
    assert agent.usage["refusals"] == 1 and agent.usage["truncated"] == 1


def test_begin_episode_resets_history():
    agent, fake = make([([block("text", "x")], "end_turn"), ([block("text", "y")], "end_turn")])
    obs = {"top": "a", "spec": "S", "feedback": "", "turns_left": 1}
    agent.act(obs)
    agent.begin_episode(obs)
    agent.act(obs)
    assert len(fake.calls[1]["messages"]) == 1


def test_retry_prompt_without_feedback_has_no_diagnostics():
    agent, fake = make([([block("text", "a")], "end_turn"), ([block("text", "b")], "end_turn")])
    obs = {"top": "a", "spec": "S", "feedback": "", "turns_left": 2}
    agent.act(obs)
    agent.act(dict(obs, turns_left=1))
    retry = fake.calls[1]["messages"][-1]["content"]
    assert "not accepted" in retry and "Tool feedback" not in retry


@pytest.mark.parametrize("task_kind", [None, "design", "repair", "verify"])
def test_system_prompt_matches_task_kind_across_retries_and_forks(task_kind):
    agent, fake = make([([block("text", "module rtl_checker; endmodule")], "end_turn") for _ in range(3)])
    obs = {"top": "rtl_checker", "spec": "SPEC", "feedback": "", "turns_left": 3}
    if task_kind is not None:
        obs["task_kind"] = task_kind
    if task_kind == "repair":
        obs.update(starter_code="module rtl_checker; endmodule", starter_feedback="Broken")
    agent.begin_episode(obs)
    agent.act(obs)
    retry = {"top": "rtl_checker", "spec": "SPEC", "feedback": "Fix the checker", "turns_left": 2}
    agent.act(retry)
    agent.fork().act({**retry, "feedback": "", "turns_left": 1})
    expected = VERIFY_SYSTEM_PROMPT if task_kind == "verify" else SYSTEM_PROMPT
    assert all(call["system"] == expected for call in fake.calls)
    if task_kind != "verify":
        assert hashlib.sha256(expected.encode()).hexdigest() == (
            "d19ee989e4d29b8e6fdef1a7fdcf691324d0bf784cb7011723dc975850fe8269"
        )


def test_direct_verify_act_and_episode_reset_select_fresh_system_prompt():
    agent, fake = make([([block("text", "module rtl_checker; endmodule")], "end_turn") for _ in range(4)])
    obs = {"top": "rtl_checker", "spec": "SPEC", "feedback": "", "turns_left": 1}
    agent.act({**obs, "task_kind": "verify"})
    for kind in ("design", "repair", "verify"):
        current = {**obs, "task_kind": kind}
        agent.begin_episode(current)
        agent.act(current)
    assert [call["system"] for call in fake.calls] == [
        VERIFY_SYSTEM_PROMPT, SYSTEM_PROMPT, SYSTEM_PROMPT, VERIFY_SYSTEM_PROMPT,
    ]
    assert all(len(call["messages"]) == 1 for call in fake.calls)
