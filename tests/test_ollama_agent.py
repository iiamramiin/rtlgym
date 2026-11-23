"""The Ollama agent is tested against a small fake Ollama server, so no model,
GPU, or Ollama install is needed."""
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from rtlgym.agents import make_agent
from rtlgym.agents.claude import SYSTEM_PROMPT, VERIFY_SYSTEM_PROMPT, ClaudeAgent
from rtlgym.agents.ollama import (
    DEFAULT_MAX_TOKENS,
    NO_ANSWER,
    OllamaAgent,
    model_info,
    normalize_host,
    strip_thinking,
)

GOOD = "module a(input x, output y);\n  assign y = x;\nendmodule"
TAGS = {"models": [{"name": "qwen3:14b", "model": "qwen3:14b", "size": 9276198565,
                    "digest": "bdbd181c33f2abc", "details": {
                        "format": "gguf", "family": "qwen3", "parameter_size": "14.8B",
                        "quantization_level": "Q4_K_M"}},
                   {"name": "llama3.1:8b", "model": "llama3.1:8b", "size": 4920753328,
                    "digest": "46e0c10c039eabc", "details": {"quantization_level": "Q4_K_M"}}]}
CAPS = {"qwen3:14b": ["completion", "tools", "thinking"], "llama3.1:8b": ["completion", "tools"]}


class FakeOllama:
    """Serves /api/chat from a queue of replies (recording each request), plus
    /api/tags, /api/show, and /api/version."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests: list[dict] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, obj, status=200):
                data = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # noqa: N802
                self._send(TAGS if self.path == "/api/tags" else {"version": "0.13.0"})

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/api/show":
                    self._send({"capabilities": CAPS.get(body["model"], ["completion"])})
                    return
                fake.requests.append(body)
                reply = dict(fake.replies.pop(0))
                time.sleep(reply.pop("_sleep", 0))
                self._send(reply, reply.pop("_status", 200))

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
            "prompt_eval_count": 100, "eval_count": 20,
            "total_duration": 2_500_000_000, "eval_duration": 2_000_000_000, **extra}


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
    # The reply text is returned as is (reasoning removed); the environment extracts.
    assert out1 == "Here it is:\n```verilog\n" + GOOD + "\n```"
    out2 = agent.act(dict(OBS, feedback="Hidden tests: 1/3 passed", turns_left=2))
    assert "~x" in out2

    first, second = srv.requests
    assert first["model"] == "qwen3:14b" and first["stream"] is False
    assert first["options"] == {"num_ctx": 8192, "num_predict": DEFAULT_MAX_TOKENS}
    assert "think" not in first  # model default unless asked
    assert [m["role"] for m in second["messages"]] == ["system", "user", "assistant", "user"]
    assert second["messages"][0]["content"] == SYSTEM_PROMPT
    assert "long reasoning" not in second["messages"][2]["content"]
    assert "Here it is" in second["messages"][2]["content"]
    assert "Hidden tests: 1/3 passed" in second["messages"][3]["content"]
    u = agent.usage
    assert u["calls"] == 2 and u["input_tokens"] == 200 and u["output_tokens"] == 40
    assert u["generate_s"] == 5.0 and u["eval_s"] == 4.0   # Ollama's own timings


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
    outs = {}
    for name, agent in (("ollama", ollama), ("claude", claude)):
        agent.begin_episode(OBS)
        outs[name] = [agent.act(obs) for obs in seq]
    ollama_users = [m["content"] for m in srv.requests[-1]["messages"] if m["role"] == "user"]
    claude_users = [m["content"] for m in calls[-1]["messages"] if m["role"] == "user"]
    assert ollama_users == claude_users
    assert calls[-1]["system"] == srv.requests[-1]["messages"][0]["content"]
    assert outs["ollama"] == outs["claude"]   # both return the reply text unchanged


def test_options_seed_and_max_tokens(server):
    srv = server([chat(GOOD), chat(GOOD)])
    OllamaAgent(model="m", host=srv.url, max_tokens=4096, seed=7).act(OBS)
    OllamaAgent(model="m", host=srv.url, options={"temperature": 0.2}).act(OBS)
    assert srv.requests[0]["options"]["num_predict"] == 4096
    assert srv.requests[0]["options"]["seed"] == 7
    assert srv.requests[1]["options"]["temperature"] == 0.2
    assert srv.requests[1]["options"]["num_predict"] == DEFAULT_MAX_TOKENS


def test_think_is_sent_only_to_models_that_support_it(server):
    srv = server([chat(GOOD) for _ in range(3)])
    qwen = OllamaAgent(model="qwen3:14b", host=srv.url, think=True)
    qwen.act(OBS)
    llama = OllamaAgent(model="llama3.1:8b", host=srv.url, think=True)
    llama.act(OBS)
    OllamaAgent(model="llama3.1:8b", host=srv.url, think=False).act(OBS)
    assert srv.requests[0]["think"] is True and not qwen.think_ignored
    # think=true to a model without a reasoning mode is an HTTP 400 in Ollama.
    assert "think" not in srv.requests[1] and llama.think_ignored
    assert llama.settings()["think_ignored"] is True
    assert srv.requests[2]["think"] is False      # think=false is always accepted


def test_truncation_and_empty_answers(server):
    srv = server([chat("<think>never finishes", done_reason="length"), chat(GOOD)])
    agent = OllamaAgent(model="m", host=srv.url)
    agent.begin_episode(OBS)
    assert agent.act(OBS) == ""
    assert agent.usage["truncated"] == 1
    agent.act(dict(OBS, feedback="no module", turns_left=2))
    history = srv.requests[1]["messages"]
    assert history[2] == {"role": "assistant", "content": NO_ANSWER}   # never empty


def test_context_overflow_is_detected(server, capsys):
    srv = server([chat(GOOD, prompt_eval_count=8100),
                  chat(GOOD, prompt_eval_count=5000, eval_count=2936),
                  chat(GOOD, prompt_eval_count=5000, eval_count=2935)])
    agent = OllamaAgent(model="m", host=srv.url, num_ctx=8192)
    for expected in (1, 2, 2):
        agent.act(OBS)
        assert agent.usage["ctx_truncated"] == expected
    assert agent.usage["max_context_tokens"] == 8120
    warnings = capsys.readouterr().err
    assert "8120 of 8192 context tokens" in warnings
    assert "7936 of 8192 context tokens" in warnings
    assert "7935 of 8192 context tokens" not in warnings


def test_context_check_uses_effective_options_and_forks_reset_the_peak(server):
    srv = server([chat(GOOD, prompt_eval_count=1000, eval_count=2840)])
    agent = OllamaAgent(model="m", host=srv.url, num_ctx=8192, options={"num_ctx": 4096})
    agent.act(OBS)
    assert agent.usage["ctx_truncated"] == 1
    assert agent.usage["max_context_tokens"] == 3840
    branch = agent.fork()
    assert branch.usage["max_context_tokens"] == 0
    assert agent.usage["max_context_tokens"] == 3840


def test_timeouts_are_not_retried(server):
    srv = server([dict(chat(GOOD), _sleep=1.5), chat(GOOD)])
    agent = OllamaAgent(model="m", host=srv.url, timeout_s=0.5, max_retries=2)
    with pytest.raises(RuntimeError, match="no reply from Ollama within"):
        agent.act(OBS)
    time.sleep(1.2)
    assert len(srv.requests) == 1 and agent.usage["calls"] == 0


def test_server_error_is_retried_and_timed_from_ollama(server):
    srv = server([{"_status": 500, "error": "busy"}, chat(GOOD)])
    agent = OllamaAgent(model="m", host=srv.url, max_retries=1)
    assert agent.act(OBS).strip() == GOOD
    assert len(srv.requests) == 2
    assert agent.usage["generate_s"] == 2.5     # the successful call only, no backoff


def test_missing_model_gives_a_clear_error(server):
    srv = server([{"_status": 404, "error": "model 'nope' not found"}])
    agent = OllamaAgent(model="nope", host=srv.url, max_retries=0)
    with pytest.raises(RuntimeError, match="ollama pull nope"):
        agent.act(OBS)


def test_server_not_running_gives_a_clear_error():
    agent = OllamaAgent(model="m", host="http://127.0.0.1:9", max_retries=0, timeout_s=2)
    with pytest.raises(RuntimeError, match="cannot reach Ollama"):
        agent.act(OBS)


def test_model_info_records_the_build(server):
    srv = server([])
    info = model_info("qwen3:14b", srv.url)
    assert info["digest"] == "bdbd181c33f2abc" and info["quantization"] == "Q4_K_M"
    assert info["parameter_size"] == "14.8B" and "thinking" in info["capabilities"]
    assert info["ollama_version"] == "0.13.0"
    assert "tags_error" in model_info("m", "http://127.0.0.1:9")   # best effort


def test_fork_continues_the_conversation_separately(server):
    srv = server([chat(GOOD), chat("A"), chat("B")])
    agent = OllamaAgent(model="m", host=srv.url)
    agent.begin_episode(OBS)
    agent.act(OBS)
    branch = agent.fork()
    agent.act(dict(OBS, feedback="full feedback", turns_left=2))
    branch.act(dict(OBS, feedback="", turns_left=2))
    assert len(agent.messages) == len(branch.messages) == 4
    assert agent.messages[:2] == branch.messages[:2]
    assert agent.messages[3]["content"] == "A" and branch.messages[3]["content"] == "B"
    assert branch.usage["calls"] == 1 and agent.usage["calls"] == 2


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


@pytest.mark.parametrize("text,expected", [
    ("<think>x</think>\nanswer", "answer"),
    ("<THINK>x</THINK>answer", "answer"),
    ("reasoning without an opening tag...</think>\n\nanswer", "answer"),
    ("<think>still thinking about module a", ""),
    ("no reasoning at all", "no reasoning at all"),
])
def test_strip_thinking(text, expected):
    assert strip_thinking(text) == expected


# ------------------------------------------------------------ end to end
@pytest.mark.needs_tools
def test_cli_run_with_ollama_end_to_end(server, tmp_path):
    from rtlgym.cli import main
    from rtlgym.task import load_task

    ref = load_task("popcount16").ref_path.read_text()
    # Prose around a bare module: the shared extractor must still find it.
    srv = server([chat("<think>plan</think>\nHere you go:\n" + ref + "\nHope it helps.")])
    out = tmp_path / "r.json"
    rc = main(["run", "--agent", "ollama", "--model", "qwen3:14b", "--ollama-host", srv.url,
               "--tasks", "popcount16", "--samples", "1", "--max-turns", "3",
               "--feedback", "none", "--workers", "1", "--seed", "11", "--out", str(out)])
    assert rc == 0
    s = json.loads(out.read_text())["summary"]
    assert s["agent"] == "ollama" and s["model"] == "qwen3:14b"
    assert s["pass@1"] == 1.0 and s["pass@1_count"] == "1/1" and s["errors"] == 0
    o = s["ollama"]
    assert o["host"] == srv.url and o["options"]["num_ctx"] == 16384
    assert o["options"]["num_predict"] == DEFAULT_MAX_TOKENS
    assert o["build"]["digest"] == "bdbd181c33f2abc" and o["build"]["quantization"] == "Q4_K_M"
    assert s["seed"]["base"] == 11 and srv.requests[0]["options"]["seed"] == 11
    assert s["tools"]["cocotb"]


def test_cli_rejects_bad_combinations():
    from rtlgym.cli import main
    with pytest.raises(SystemExit, match="needs --model"):
        main(["run", "--agent", "ollama"])
    with pytest.raises(SystemExit, match="Claude agent only"):
        main(["run", "--agent", "ollama", "--model", "m", "--effort", "low"])
    with pytest.raises(SystemExit, match="ollama only"):
        main(["run", "--agent", "replay", "--seed", "1"])


@pytest.mark.parametrize("task_kind", [None, "design", "repair", "verify"])
def test_system_prompt_matches_task_kind_across_retries_and_forks(server, task_kind):
    srv = server([chat(GOOD) for _ in range(3)])
    agent = OllamaAgent(model="m", host=srv.url)
    obs = {**OBS, "top": "rtl_checker"}
    if task_kind is not None:
        obs["task_kind"] = task_kind
    if task_kind == "repair":
        obs.update(starter_code=GOOD, starter_feedback="Broken")
    agent.begin_episode(obs)
    agent.act(obs)
    retry = {**OBS, "feedback": "Fix the checker", "turns_left": 2}
    agent.act(retry)
    agent.fork().act({**retry, "feedback": "", "turns_left": 1})
    expected = VERIFY_SYSTEM_PROMPT if task_kind == "verify" else SYSTEM_PROMPT
    assert all(request["messages"][0] == {"role": "system", "content": expected}
               for request in srv.requests)
    if task_kind != "verify":
        assert hashlib.sha256(expected.encode()).hexdigest() == (
            "d19ee989e4d29b8e6fdef1a7fdcf691324d0bf784cb7011723dc975850fe8269"
        )


def test_direct_verify_act_and_episode_reset_select_fresh_system_prompt(server):
    srv = server([chat(GOOD) for _ in range(4)])
    agent = OllamaAgent(model="m", host=srv.url)
    agent.act({**OBS, "task_kind": "verify"})
    for kind in ("design", "repair", "verify"):
        current = {**OBS, "task_kind": kind}
        agent.begin_episode(current)
        agent.act(current)
    assert [request["messages"][0]["content"] for request in srv.requests] == [
        VERIFY_SYSTEM_PROMPT, SYSTEM_PROMPT, SYSTEM_PROMPT, VERIFY_SYSTEM_PROMPT,
    ]
    assert all(len(request["messages"]) == 2 for request in srv.requests)


@pytest.mark.parametrize("task,kind", [
    ("popcount16", "design"),
    ("repair_popcount16", "repair"),
    ("verify_popcount16", "verify"),
])
def test_paired_local_cli_preserves_prompts_truncation_and_reproducibility(
        server, monkeypatch, tmp_path, task, kind):
    from rtlgym import cli
    from rtlgym.evaluator import EvalResult

    def reject(task, code, *args, **kwargs):
        result = EvalResult(task.id, "example", violations=["incomplete source"])
        if task.kind == "verify":
            result.verification = {"status": "invalid", "caught": 0, "mutants_total": 0,
                                   "weighted_caught": 0.0, "families": {}}
        return result

    versions = {"cocotb": "2.1.0", "iverilog": "Icarus Verilog 12.0", "verilator": "5.020",
                "yosys": "0.33", "sv2v": "v0.0.13"}
    monkeypatch.setattr("rtlgym.env.evaluate", reject)
    monkeypatch.setattr(cli, "tool_versions", lambda: dict(versions))
    monkeypatch.setattr(cli, "_git_commit", lambda: "example")
    srv = server([
        chat("<think>unfinished", done_reason="length", eval_count=2048),
        chat("module incomplete("),
        chat("module incomplete("),
    ])
    out = tmp_path / "paired.json"
    assert cli.main([
        "run", "--agent", "ollama", "--model", "qwen3:14b", "--ollama-host", srv.url,
        "--tasks", task, "--samples", "1", "--max-turns", "2", "--paired", "--workers", "1",
        "--num-ctx", "4096", "--max-tokens", "2048", "--think", "off", "--seed", "41",
        "--no-cache", "--out", str(out),
    ]) == 0
    assert len(srv.requests) == 3  # one shared first attempt, one retry in each arm
    expected_prompt = VERIFY_SYSTEM_PROMPT if kind == "verify" else SYSTEM_PROMPT
    for request in srv.requests:
        assert request["messages"][0] == {"role": "system", "content": expected_prompt}
        assert request["options"] == {"num_ctx": 4096, "num_predict": 2048, "seed": 41}
        assert request["think"] is False

    files = sorted(tmp_path.glob("*.json"))
    assert len(files) == 3
    for path in files:
        saved = json.loads(path.read_text())
        meta = saved.get("summary", saved.get("meta"))
        settings = meta["ollama"]
        assert settings["build"]["ollama_version"] == "0.13.0"
        assert settings["build"]["digest"] == "bdbd181c33f2abc"
        assert settings["build"]["quantization"] == "Q4_K_M"
        assert settings["options"] == {"num_ctx": 4096, "num_predict": 2048, "seed": 41}
        assert settings["think"] is settings["think_requested"] is False
        assert not settings["think_ignored"]
        assert meta["seed"] == {"base": 41, "per_episode": "base + episode index"}
        assert meta["tools"] == versions
        if "episodes" in saved:
            episode = saved["episodes"][0]
            first, retry = episode["trajectory"]
            assert episode["task_kind"] == kind
            assert first["report_status"] == "truncated"
            assert first["usage"]["truncated"] == 1 and first["score"] == first["reward"] == 0
            assert "report_status" not in retry and retry["usage"]["truncated"] == 0
            assert episode["usage"]["calls"] == 1 and episode["usage"]["truncated"] == 0
            assert episode["shared_first"]["usage"]["calls"] == 1
            assert meta["truncated_attempts"] == 1
        else:
            assert saved["paired"]["shared_first"]["calls"] == 1
            assert saved["paired"]["shared_first"]["truncated"] == 1
