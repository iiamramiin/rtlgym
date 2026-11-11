"""The Claude agent is tested with a fake client, so no API key or network is needed."""
from types import SimpleNamespace

from rtlgym.agents.claude import ClaudeAgent


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def test_conversation_carries_feedback_across_turns():
    fake = FakeMessages(["```verilog\nmodule a; endmodule\n```", "```verilog\nmodule b; endmodule\n```"])
    agent = ClaudeAgent(model="test-model", client=SimpleNamespace(messages=fake))
    obs = {"top": "a", "spec": "SPEC", "feedback": "", "turns_left": 3}
    agent.begin_episode(obs)
    assert "module a" in agent.act(obs)
    obs2 = dict(obs, feedback="Hidden tests: 1/3 passed", turns_left=2)
    assert "module b" in agent.act(obs2)
    second = fake.calls[1]
    assert second["model"] == "test-model"
    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    assert "Hidden tests: 1/3 passed" in second["messages"][-1]["content"]
    assert agent.usage == {"input_tokens": 20, "output_tokens": 10}


def test_begin_episode_resets_history():
    fake = FakeMessages(["x", "y"])
    agent = ClaudeAgent(client=SimpleNamespace(messages=fake))
    obs = {"top": "a", "spec": "S", "feedback": "", "turns_left": 1}
    agent.act(obs)
    agent.begin_episode(obs)
    agent.act(obs)
    assert len(fake.calls[1]["messages"]) == 1
