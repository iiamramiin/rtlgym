# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

from .base import Agent
from .replay import ReplayAgent

__all__ = ["Agent", "ReplayAgent", "make_agent"]


def make_agent(name: str, **kwargs) -> Agent:
    if name == "replay":
        return ReplayAgent(**kwargs)
    if name == "claude":
        from .claude import ClaudeAgent  # optional dependency
        return ClaudeAgent(**kwargs)
    if name == "ollama":
        from .ollama import OllamaAgent  # local models; standard library only
        return OllamaAgent(**kwargs)
    raise ValueError(f"unknown agent '{name}' (choose 'replay', 'claude', or 'ollama')")
