"""The Ollama agent is tested against a small fake Ollama server, so no model,
GPU, or Ollama install is needed."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from rtlgym.agents import make_agent
from rtlgym.agents.claude import SYSTEM_PROMPT, ClaudeAgent
from rtlgym.agents.ollama import OllamaAgent, extract_module, normalize_host, strip_thinking

GOOD = "module a(input x, output y);\n  assign y = x;\nendmodule"


class FakeOllama:
    """Serves POST /api/chat from a queue of replies and records each request."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests: list[dict] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(body)
                reply = fake.replies.pop(0)
                status = reply.pop("_status", 200)
                data = json.dumps(reply).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def chat(content="", thinking=None, done_reason="stop", **extra):
    msg = {"role": "assistant", "content": content}
    if thinking is not None:
        msg["thinking"] = thinking
    return {"model": "m", "message": msg, "done": True, "done_reason": done_reason,
            "prompt_eval_count": 100, "eval_count": 20, **extra}


@pytest.fixture
def server():
    servers = []

    def start(replies):
        s = FakeOllama(replies)
        servers.append(s)
        return s

    yield start
    for s in servers:
        s.close()


OBS = {"top": "a", "spec": "SPEC", "feedback": "", "turns_left": 3}


def test_conversation_carries_feedback_and_drops_reasoning(server):
    srv = server([
        chat("<think>long reasoning</think>\nHere it is:\n```verilog\n" + GOOD + "\n```"),
        chat("```systemverilog\n" + GOOD.replace("x;", "~x;") + "\n```", thinking="hmm"),
    ])
    agent = OllamaAgent(model="qwen3:14b", host=srv.url, num_ctx=8192)
    agent.begin_episode(OBS)
    out1 = agent.act(OBS)
    assert out1.startswith("```systemverilog\nmodule a") and "<think>" not in out1
    out2 = agent.act(dict(OBS, feedback="Hidden tests: 1/3 passed", turns_left=2))
    assert "~x" in out2

    first, second = srv.requests
    assert first["model"] == "qwen3:14b" and first["stream"] is False
    assert first["options"]["num_ctx"] == 8192
    assert "think" not in first  # model default unless asked
    assert [m["role"] for m in second["messages"]] == ["system", "user", "assistant", "user"]
    assert second["messages"][0]["content"] == SYSTEM_PROMPT
    # Earlier reasoning is not sent back; the answer is.
    assert "long reasoning" not in second["messages"][2]["content"]
    assert "Here it is" in second["messages"][2]["content"]
    assert "Hidden tests: 1/3 passed" in second["messages"][3]["content"]
    assert agent.usage["calls"] == 2
    assert agent.usage["input_tokens"] == 200 and agent.usage["output_tokens"] == 40


def test_user_messages_match_the_claude_agent(server):
    """Both agents must see the same prompts, or the comparison is unfair."""
    seq = [OBS, dict(OBS, feedback="Score: 0.1", turns_left=2),
           dict(OBS, feedback="", turns_left=1)]  # the last is the feedback="none" retry
    srv = server([chat(GOOD) for _ in seq])
    ollama = OllamaAgent(model="m", host=srv.url)

    calls = []

    class FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=GOOD)],
                                   stop_reason="end_turn",
                                   usage=SimpleNamespace(input_tokens=1, output_tokens=1))

    def stream(**kw):
        calls.append(kw)
        return FakeStream()

    claude = ClaudeAgent(client=SimpleNamespace(messages=SimpleNamespace(stream=stream)))
    for agent in (ollama, claude):
        agent.begin_episode(OBS)
        for obs in seq:
            agent.act(obs)
    ollama_users = [m["content"] for m in srv.requests[-1]["messages"] if m["role"] == "user"]
    claude_users = [m["content"] for m in calls[-1]["messages"] if m["role"] == "user"]
    assert ollama_users == claude_users
    assert calls[-1]["system"] == srv.requests[-1]["messages"][0]["content"]


def test_think_and_max_tokens_options(server):
    srv = server([chat(GOOD), chat(GOOD)])
    OllamaAgent(model="m", host=srv.url, think=False, max_tokens=4096).act(OBS)
    OllamaAgent(model="m", host=srv.url, think=True,
                options={"temperature": 0.2}).act(OBS)
    assert srv.requests[0]["think"] is False
    assert srv.requests[0]["options"]["num_predict"] == 4096
    assert srv.requests[1]["think"] is True
    assert srv.requests[1]["options"]["temperature"] == 0.2


def test_truncation_counted(server):
    srv = server([chat("```verilog\nmodule a(input x);\n", done_reason="length")])
    agent = OllamaAgent(model="m", host=srv.url)
    out = agent.act(OBS)
    assert agent.usage["truncated"] == 1
    assert "module a(input x);" in out  # unclosed fence still yields the code


def test_missing_model_gives_a_clear_error(server):
    srv = server([{"_status": 404, "error": "model 'nope' not found"}])
    agent = OllamaAgent(model="nope", host=srv.url, max_retries=0)
    with pytest.raises(RuntimeError, match="ollama pull nope"):
        agent.act(OBS)


def test_server_not_running_gives_a_clear_error():
    agent = OllamaAgent(model="m", host="http://127.0.0.1:9", max_retries=0, timeout_s=2)
    with pytest.raises(RuntimeError, match="cannot reach Ollama"):
        agent.act(OBS)


def test_server_error_is_retried(server):
    srv = server([{"_status": 500, "error": "busy"}, chat(GOOD)])
    agent = OllamaAgent(model="m", host=srv.url, max_retries=1)
    assert "module a" in agent.act(OBS)
    assert len(srv.requests) == 2


def test_model_is_required(monkeypatch):
    monkeypatch.delenv("RTLGYM_OLLAMA_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="--model"):
        OllamaAgent()


def test_make_agent_builds_ollama():
    agent = make_agent("ollama", model="llama3.1:8b", host="localhost")
    assert isinstance(agent, OllamaAgent) and agent.host == "http://localhost:11434"


@pytest.mark.parametrize("given,expected", [
    (None, "http://localhost:11434"),
    ("0.0.0.0:11434", "http://localhost:11434"),
    ("127.0.0.1:11500", "http://127.0.0.1:11500"),
    ("http://192.168.1.5:11434/", "http://192.168.1.5:11434"),
    ("myhost", "http://myhost:11434"),
])
def test_normalize_host(given, expected, monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert normalize_host(given) == expected


def test_host_from_environment(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "0.0.0.0:11500")
    assert normalize_host(None) == "http://localhost:11500"


# ------------------------------------------------------------ extraction
@pytest.mark.parametrize("reply", [
    "```systemverilog\n" + GOOD + "\n```",
    "```verilog\n" + GOOD + "\n```",
    "```sv\n" + GOOD + "\n```",
    "```\n" + GOOD + "\n```",
    "~~~verilog\n" + GOOD + "\n~~~",
    "Sure! Here is the design:\n\n```systemverilog\n" + GOOD + "\n```\n\nIt assigns y = x.",
    GOOD,
    "The module is below.\n" + GOOD + "\nThis should pass the tests.",
    "<think>\nmodule wrong; endmodule\n</think>\n```verilog\n" + GOOD + "\n```",
    "reasoning without an opening tag...</think>\n\n" + GOOD,
    "<THINK>x</THINK>```verilog\n" + GOOD + "\n```",
])
def test_extract_module_variants(reply):
    code = extract_module(reply, "a")
    assert code.startswith("module a(") and code.rstrip().endswith("endmodule")


def test_extract_prefers_the_block_with_the_top_module():
    reply = ("```verilog\nmodule a(input x, output y); assign y = x; endmodule\n```\n"
             "Testbench:\n```verilog\nmodule tb; endmodule\n```")
    assert extract_module(reply, "a").startswith("module a(")
    # Without a top name, the last block with a module wins (same rule as extract_code).
    assert extract_module(reply).startswith("module tb")


def test_extract_keeps_helper_modules_outside_fences():
    reply = "module helper(); endmodule\n\nmodule a(); helper u(); endmodule\nDone."
    code = extract_module(reply, "a")
    assert code.startswith("module helper") and code.rstrip().endswith("endmodule")


def test_unfinished_reasoning_yields_no_code():
    assert strip_thinking("<think>still thinking about module a") == ""
    assert extract_module("<think>module a; endmodule", "a") == "\n"


# ------------------------------------------------------------ end to end
@pytest.mark.needs_tools
def test_cli_run_with_ollama_end_to_end(server, tmp_path):
    from rtlgym.cli import main
    from rtlgym.task import load_task

    ref = load_task("popcount16").ref_path.read_text()
    srv = server([chat("<think>plan</think>\n```systemverilog\n" + ref + "```")])
    out = tmp_path / "r.json"
    rc = main(["run", "--agent", "ollama", "--model", "qwen3:14b", "--ollama-host", srv.url,
               "--tasks", "popcount16", "--samples", "1", "--max-turns", "3",
               "--feedback", "none", "--workers", "1", "--out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text())
    s = data["summary"]
    assert s["agent"] == "ollama" and s["model"] == "qwen3:14b"
    assert s["ollama"]["host"] == srv.url and s["ollama"]["num_ctx"] == 16384
    assert s["pass@1"] == 1.0 and s["errors"] == 0
    assert s["usage"]["calls"] == 1


def test_cli_rejects_effort_and_missing_model():
    from rtlgym.cli import main
    with pytest.raises(SystemExit, match="needs --model"):
        main(["run", "--agent", "ollama"])
    with pytest.raises(SystemExit, match="Claude agent only"):
        main(["run", "--agent", "ollama", "--model", "m", "--effort", "low"])
