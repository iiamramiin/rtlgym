# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""LLM agent backed by a local model served by Ollama (no API key needed).

Talks to Ollama's HTTP API (POST /api/chat) using only the standard library.
The conversation is kept across turns, so the model sees its own previous
attempt and the tool feedback, like the Claude agent. The system prompt and the
per-turn user messages are the same as the Claude agent's, and the reply text is
returned as is: the environment extracts the RTL with the same function for
every agent (checks.extract_code).

Local models differ from the Claude API in a few ways this agent handles:
- Some models (e.g. Qwen3) reason before answering, either in a separate
  ``thinking`` field or inline as ``<think>...</think>``. Reasoning is removed
  from the reply and from the stored history (Qwen3's own chat template drops
  earlier reasoning too), the same way the Claude agent returns only text blocks.
- Ollama's default context window is small and silently truncates long
  conversations, so the agent sets ``num_ctx`` and warns if a prompt fills it.
- Output is capped (``num_predict``, default 8192) so a looping model stops.
- Generation is slow on a laptop, so the request timeout is long and a timed-out
  request is not retried (a retry would regenerate the whole answer).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from .base import Agent

# Same system prompt as the Claude agent, so the two are compared on equal terms.
from .claude import SYSTEM_PROMPT

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_TIMEOUT_S = 1800.0
DEFAULT_NUM_CTX = 16384
DEFAULT_MAX_TOKENS = 8192
CTX_MARGIN = 256          # prompt tokens this close to num_ctx count as possibly truncated
NO_ANSWER = "(no answer)"


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


def _is_timeout(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    return isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError)


def _get_json(url: str, payload: dict | None = None, timeout: float = 15.0) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def model_info(model: str, host: str | None = None) -> dict:
    """The exact model build, for result metadata: digest, quantization, size,
    family, and capabilities (from /api/tags and /api/show). Best effort."""
    base = normalize_host(host)
    info: dict = {"model": model}
    try:
        for m in _get_json(base + "/api/tags").get("models", []):
            if m.get("name") == model or m.get("model") == model:
                d = m.get("details") or {}
                info.update(digest=m.get("digest"), size_bytes=m.get("size"),
                            family=d.get("family"), parameter_size=d.get("parameter_size"),
                            quantization=d.get("quantization_level"), format=d.get("format"))
                break
    except Exception as exc:  # noqa: BLE001
        info["tags_error"] = str(exc)[:200]
    try:
        info["capabilities"] = _get_json(base + "/api/show", {"model": model}).get("capabilities")
    except Exception as exc:  # noqa: BLE001
        info["show_error"] = str(exc)[:200]
    try:
        info["ollama_version"] = _get_json(base + "/api/version").get("version")
    except Exception:  # noqa: BLE001
        pass
    return info


class OllamaAgent(Agent):
    def __init__(self, model: str | None = None, host: str | None = None,
                 timeout_s: float = DEFAULT_TIMEOUT_S, num_ctx: int = DEFAULT_NUM_CTX,
                 max_tokens: int | None = DEFAULT_MAX_TOKENS, think: bool | None = None,
                 seed: int | None = None, options: dict | None = None, max_retries: int = 2):
        model = model or os.environ.get("RTLGYM_OLLAMA_MODEL")
        if not model:
            raise RuntimeError("pass --model with an installed Ollama model, e.g. qwen3:14b "
                               "(see `ollama list`)")
        self.model = model
        self.host = normalize_host(host)
        self.timeout_s = timeout_s
        self.think = think
        self.max_retries = max_retries
        self.num_ctx = num_ctx
        self.options: dict = {"num_ctx": num_ctx,
                              "num_predict": max_tokens or DEFAULT_MAX_TOKENS}
        if seed is not None:
            self.options["seed"] = seed
        self.options.update(options or {})
        self._capabilities: list[str] | None = None
        self.think_ignored = False
        self.messages: list[dict] = []
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                      "refusals": 0, "truncated": 0, "ctx_truncated": 0,
                      "generate_s": 0.0, "eval_s": 0.0}

    # ----------------------------------------------------------- the episode
    def begin_episode(self, obs: dict) -> None:
        self.messages = []

    def act(self, obs: dict) -> str:
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
        answer = strip_thinking(self._call().get("content") or "")
        # Store the answer without reasoning (smaller context, as the chat template
        # expects); an empty turn would leave the history invalid for the next call.
        self.messages.append({"role": "assistant", "content": answer or NO_ANSWER})
        return answer  # raw text; the environment extracts the RTL

    # ------------------------------------------------------------ settings
    def settings(self) -> dict:
        """What was actually sent, for result metadata."""
        return {"host": self.host, "options": dict(self.options),
                "think": self._think_to_send(), "think_requested": self.think,
                "think_ignored": self.think_ignored, "timeout_s": self.timeout_s}

    def _capabilities_list(self) -> list[str] | None:
        if self._capabilities is None:
            try:
                caps = _get_json(self.host + "/api/show", {"model": self.model}).get("capabilities")
                self._capabilities = list(caps) if caps is not None else []
            except Exception:  # noqa: BLE001 - older servers: send what was asked
                self._capabilities = []
                return None
        return self._capabilities

    def _think_to_send(self) -> bool | None:
        if self.think is None:
            return None
        if self.think is False:
            return False                       # always accepted by Ollama
        caps = self._capabilities_list()
        if caps is not None and caps and "thinking" not in caps:
            self.think_ignored = True          # think=true would be an HTTP 400
            return None
        return True

    # ------------------------------------------------------------------ HTTP
    def _post(self, path: str, payload: dict) -> dict:
        return _get_json(self.host + path, payload, timeout=self.timeout_s)

    def _call(self) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *self.messages],
            "stream": False,
            "options": self.options,
        }
        think = self._think_to_send()
        if think is not None:
            payload["think"] = think
        for attempt in range(self.max_retries + 1):
            t0 = time.monotonic()
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
                if _is_timeout(exc):
                    # Retrying would regenerate the whole answer for up to timeout_s more.
                    raise RuntimeError(f"no reply from Ollama within {self.timeout_s:.0f} s "
                                       "(--ollama-timeout)") from exc
                if attempt == self.max_retries:
                    raise RuntimeError(f"cannot reach Ollama at {self.host} ({exc}); is "
                                       "`ollama serve` (or the Ollama app) running?") from exc
            time.sleep(min(30, 2 ** attempt))
        wall = time.monotonic() - t0
        u = self.usage
        u["calls"] += 1
        # Time for the successful call only, from Ollama's own counters (nanoseconds).
        total_ns, eval_ns = data.get("total_duration"), data.get("eval_duration")
        u["generate_s"] = round(u["generate_s"] + (total_ns / 1e9 if total_ns else wall), 2)
        u["eval_s"] = round(u["eval_s"] + (eval_ns / 1e9 if eval_ns else 0.0), 2)
        prompt_tokens = int(data.get("prompt_eval_count") or 0)
        u["input_tokens"] += prompt_tokens
        u["output_tokens"] += int(data.get("eval_count") or 0)
        if data.get("done_reason") == "length":
            u["truncated"] += 1
        if prompt_tokens >= self.num_ctx - CTX_MARGIN:
            u["ctx_truncated"] += 1
            print(f"warning: prompt used {prompt_tokens} of {self.num_ctx} context tokens; "
                  "earlier turns may have been cut. Raise --num-ctx.", file=sys.stderr)
        msg = data.get("message") or {}
        return {"content": msg.get("content", ""), "thinking": msg.get("thinking", "")}
