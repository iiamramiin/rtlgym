# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""LLM agent backed by the Claude API (optional; needs ANTHROPIC_API_KEY).

The conversation is kept across turns, so the model sees its own previous
attempt and the tool feedback, the same way an RL rollout would. Assistant turns
are stored exactly as returned (including any thinking blocks) and the
conversation is append-only, as the API expects for multi-turn use.

Current Claude models choose their own sampling settings: the request sends no
temperature. Thinking counts toward max_tokens, so the default limit is high and
responses are streamed.
"""

from __future__ import annotations

import os

from .base import Agent

SYSTEM_PROMPT = """You are an expert RTL design engineer.
Write synthesizable SystemVerilog (IEEE 1800-2012) that implements the given spec exactly.
Rules:
- Return exactly one module with the requested name and port list, in one ```systemverilog code block.
- Use only synthesizable constructs: no delays, no initial blocks for logic, no system tasks.
- Keep the code compatible with Icarus Verilog 12 (-g2012), Verilator lint, and Yosys.
- Prefer clean, lint-free code and small area once the design is correct.
When you get tool feedback, fix the reported problems and return the complete corrected module."""

DEFAULT_MODEL = "claude-sonnet-5-5"


class ClaudeAgent(Agent):
    def __init__(self, model: str | None = None, max_tokens: int = 32000,
                 effort: str | None = None, client=None, max_retries: int = 5):
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("pip install anthropic to use the Claude agent") from exc
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError("set ANTHROPIC_API_KEY to use the Claude agent")
            # The SDK retries rate limits, overloads, and connection errors itself.
            client = anthropic.Anthropic(max_retries=max_retries)
        self.client = client
        self.model = model or os.environ.get("RTLGYM_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens
        self.effort = effort
        self.messages: list[dict] = []
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                      "refusals": 0, "truncated": 0}

    def begin_episode(self, obs: dict) -> None:
        self.messages = []

    def act(self, obs: dict) -> str:
        if not self.messages:
            content = f"Implement module `{obs['top']}`.\n\n## Specification\n\n{obs['spec']}"
        elif obs["feedback"]:
            content = ("Tool feedback on your last submission:\n\n```\n" + obs["feedback"]
                       + f"\n```\n\nYou have {obs['turns_left']} attempt(s) left. "
                       "Return the full corrected module.")
        else:
            # Retry without diagnostics (feedback="none"): the control arm for measuring
            # what tool feedback adds over simply trying again.
            content = (f"Your last submission was not accepted. You have {obs['turns_left']} "
                       "attempt(s) left. Return the full module.")
        self.messages.append({"role": "user", "content": content})
        msg = self._call()
        # Keep the full assistant turn (thinking blocks included) for the next request.
        self.messages.append({"role": "assistant", "content": msg.content})
        return "".join(getattr(b, "text", "") for b in msg.content
                       if getattr(b, "type", "") == "text")

    def _call(self):
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": list(self.messages),
        }
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        with self.client.messages.stream(**kwargs) as stream:
            msg = stream.get_final_message()
        self.usage["calls"] += 1
        u = getattr(msg, "usage", None)
        if u is not None:
            self.usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
            self.usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0
        stop = getattr(msg, "stop_reason", None)
        if stop == "refusal":
            self.usage["refusals"] += 1
        elif stop == "max_tokens":
            self.usage["truncated"] += 1
        return msg
