# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""LLM agent backed by a local model served by Ollama (no API key needed).

Talks to Ollama's HTTP API (POST /api/chat) using only the standard library.
The conversation is kept across turns, so the model sees its own previous
attempt and the tool feedback, like the Claude agent. The system prompt and the
per-turn user messages are the same as the Claude agent's, so results from the
two agents are comparable.

Local models differ from the Claude API in a few ways this agent handles:
- Some models (e.g. Qwen3) reason before answering, either in a separate
  ``thinking`` field or inline as ``<think>...</think>``. Reasoning is removed
  from the reply and from the stored history (Qwen3's own chat template drops
  earlier reasoning too), which also keeps the context small.
- Ollama's default context window is small and silently truncates long
  conversations, so the agent sets ``num_ctx`` explicitly.
- Replies vary in format (no code fence, several fences, an unclosed fence when
  the output is cut off), so the module is extracted with fallbacks and returned
  in a single ``systemverilog`` fence.
- Generation is slow on a laptop, so the request timeout is long.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from .base import Agent

# Same system prompt as the Claude agent, so the two are compared on equal terms.
from .claude import SYSTEM_PROMPT

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_TIMEOUT_S = 1800.0
DEFAULT_NUM_CTX = 16384


def normalize_host(host: str | None) -> str:
    """Accept the forms OLLAMA_HOST takes ("0.0.0.0:11434", "localhost",
    "http://host:port/") and return a base URL."""
    host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).strip().rstrip("/")
    if "://" not in host:
        host = "http://" + host
    scheme, rest = host.split("://", 1)
    if rest.startswith("0.0.0.0"):  # a listen address, not one to connect to
        rest = "localhost" + rest[len("0.0.0.0"):]
    if ":" not in rest.split("/", 1)[0] and not rest.startswith("["):
        rest = rest.split("/", 1)[0] + ":11434"
    return f"{scheme}://{rest}"


_THINK_BLOCK = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.S | re.I)
_THINK_OPEN = re.compile(r"<(think|thinking|reasoning)>", re.I)
_THINK_CLOSE = re.compile(r"</(think|thinking|reasoning)>", re.I)
_FENCE = re.compile(r"(```|~~~)[ \t]*([\w+-]*)[^\n]*\n(.*?)\1", re.S)
_OPEN_FENCE = re.compile(r"(```|~~~)[ \t]*[\w+-]*[^\n]*\n", re.S)
# A module declaration starts a line ("module name (" / "#(" / ";"), so the word
# "module" in prose ("The module is below") is not mistaken for code.
_MODULE = re.compile(r"^[ \t]*module\s+[A-Za-z_]\w*\s*(?:#|\(|;).*?\bendmodule\b", re.S | re.M)


def strip_thinking(text: str) -> str:
    """Remove reasoning that some local models put in the reply text."""
    text = _THINK_BLOCK.sub("", text)
    close = list(_THINK_CLOSE.finditer(text))
    if close:  # a closing tag whose opening tag was in the prompt template
        text = text[close[-1].end():]
    m = _THINK_OPEN.search(text)
    if m:  # reasoning that never finished: nothing after it is an answer
        text = text[:m.start()]
    return text.strip()


def extract_module(text: str, top: str | None = None) -> str:
    """Return the SystemVerilog source in a model reply, or the cleaned reply
    if no module can be found. Preference order: the last code fence that
    defines ``top``; the last fence that defines any module; an unclosed fence
    (output cut off); bare ``module ... endmodule`` text; the text itself."""
    text = strip_thinking(text)

    def has_top(code: str) -> bool:
        return bool(top and re.search(rf"\bmodule\s+{re.escape(top)}\b", code))

    blocks = [m.group(3) for m in _FENCE.finditer(text)]
    with_module = [b for b in blocks if re.search(r"\bmodule\b", b)]
    for pick in ([b for b in with_module if has_top(b)], with_module):
        if pick:
            return pick[-1].strip() + "\n"

    opens = list(_OPEN_FENCE.finditer(text))
    if opens and len(re.findall(r"```|~~~", text)) % 2 == 1:
        tail = text[opens[-1].end():]
        if re.search(r"\bmodule\b", tail):
            return tail.strip() + "\n"

    mods = _MODULE.findall(text)
    if mods:
        # Keep helper modules defined next to the top module, in order.
        start = text.find(mods[0])
        end = text.rfind(mods[-1]) + len(mods[-1])
        return text[start:end].strip() + "\n"
    return text.strip() + "\n"


class OllamaAgent(Agent):
    def __init__(self, model: str | None = None, host: str | None = None,
                 timeout_s: float = DEFAULT_TIMEOUT_S, num_ctx: int = DEFAULT_NUM_CTX,
                 max_tokens: int | None = None, think: bool | None = None,
                 options: dict | None = None, max_retries: int = 2):
        model = model or os.environ.get("RTLGYM_OLLAMA_MODEL")
        if not model:
            raise RuntimeError("pass --model with an installed Ollama model, e.g. qwen3:14b "
                               "(see `ollama list`)")
        self.model = model
        self.host = normalize_host(host)
        self.timeout_s = timeout_s
        self.think = think
        self.max_retries = max_retries
        self.options: dict = {"num_ctx": num_ctx}
        if max_tokens:
            self.options["num_predict"] = max_tokens
        self.options.update(options or {})
        self.messages: list[dict] = []
        self._top: str | None = None
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                      "refusals": 0, "truncated": 0, "generate_s": 0.0}

    def begin_episode(self, obs: dict) -> None:
        self.messages = []
        self._top = obs.get("top")

    def act(self, obs: dict) -> str:
        self._top = obs.get("top", self._top)
        # The same user messages as the Claude agent (see agents/claude.py).
        if not self.messages:
            content = f"Implement module `{obs['top']}`.\n\n## Specification\n\n{obs['spec']}"
        elif obs["feedback"]:
            content = ("Tool feedback on your last submission:\n\n```\n" + obs["feedback"]
                       + f"\n```\n\nYou have {obs['turns_left']} attempt(s) left. "
                       "Return the full corrected module.")
        else:
            content = (f"Your last submission was not accepted. You have {obs['turns_left']} "
                       "attempt(s) left. Return the full module.")
        self.messages.append({"role": "user", "content": content})
        reply = self._call()
        answer = strip_thinking(reply.get("content") or "")
        # Store the answer without reasoning: smaller context, as the template expects.
        self.messages.append({"role": "assistant", "content": answer})
        return "```systemverilog\n" + extract_module(answer, self._top) + "```\n"

    # ------------------------------------------------------------------ HTTP
    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(self.host + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))

    def _call(self) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *self.messages],
            "stream": False,
            "options": self.options,
        }
        if self.think is not None:
            payload["think"] = self.think
        t0 = time.monotonic()
        for attempt in range(self.max_retries + 1):
            try:
                data = self._post("/api/chat", payload)
                break
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")[:300]
                if exc.code == 404:
                    raise RuntimeError(f"Ollama has no model '{self.model}'; run `ollama list` "
                                       f"or `ollama pull {self.model}` ({body})") from exc
                if exc.code < 500 or attempt == self.max_retries:
                    raise RuntimeError(f"Ollama HTTP {exc.code}: {body}") from exc
            except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
                if attempt == self.max_retries:
                    raise RuntimeError(f"cannot reach Ollama at {self.host} ({exc}); is "
                                       "`ollama serve` (or the Ollama app) running?") from exc
            time.sleep(min(30, 2 ** attempt))
        self.usage["calls"] += 1
        self.usage["generate_s"] = round(self.usage["generate_s"] + time.monotonic() - t0, 2)
        self.usage["input_tokens"] += int(data.get("prompt_eval_count") or 0)
        self.usage["output_tokens"] += int(data.get("eval_count") or 0)
        if data.get("done_reason") == "length":
            self.usage["truncated"] += 1
        msg = data.get("message") or {}
        return {"content": msg.get("content", ""), "thinking": msg.get("thinking", "")}
