# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""LLM agent backed by the Claude API (optional; needs ANTHROPIC_API_KEY).

The conversation is kept across turns, so the model sees its own previous
attempt and the tool feedback, the same way an RL rollout would.
"""

from __future__ import annotations

import os
import time

from .base import Agent

SYSTEM_PROMPT = """You are an expert RTL design engineer.
Write synthesizable SystemVerilog (IEEE 1800-2012) that implements the given spec exactly.
Rules:
- Return exactly one module with the requested name and port list, in one ```systemverilog code block.
- Use only synthesizable constructs: no delays, no initial blocks for logic, no system tasks.
- Keep the code compatible with Icarus Verilog 12 (-g2012), Verilator lint, and Yosys.
- Prefer clean, lint-free code and small area once the design is correct.
When you get tool feedback, fix the reported problems and return the complete corrected module."""


class ClaudeAgent(Agent):
    def __init__(self, model: str | None = None, max_tokens: int = 4096,
                 temperature: float = 0.2, client=None, max_retries: int = 3):
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("pip install anthropic to use the Claude agent") from exc
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError("set ANTHROPIC_API_KEY to use the Claude agent")
            client = anthropic.Anthropic()
        self.client = client
        self.model = model or os.environ.get("RTLGYM_MODEL", "claude-sonnet-5-5")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.messages: list[dict] = []
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    def begin_episode(self, obs: dict) -> None:
        self.messages = []

    def act(self, obs: dict) -> str:
        if not self.messages:
            content = (f"Implement module `{obs['top']}`.\n\n## Specification\n\n{obs['spec']}")
        else:
            content = ("Tool feedback on your last submission:\n\n```\n" + obs["feedback"]
                       + f"\n```\n\nYou have {obs['turns_left']} attempt(s) left. "
                       "Return the full corrected module.")
        self.messages.append({"role": "user", "content": content})
        text = self._call()
        self.messages.append({"role": "assistant", "content": text})
        return text

    def _call(self) -> str:
        delay = 2.0
        for attempt in range(self.max_retries):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=SYSTEM_PROMPT,
                    messages=list(self.messages),
                )
                u = getattr(resp, "usage", None)
                if u is not None:
                    self.usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
                    self.usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0
                return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            except Exception:  # noqa: BLE001 - retry transient API errors
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(delay)
                delay *= 2
        return ""  # pragma: no cover
