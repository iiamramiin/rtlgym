from .base import Agent
from .replay import ReplayAgent

__all__ = ["Agent", "ReplayAgent", "make_agent"]


def make_agent(name: str, **kwargs) -> Agent:
    if name == "replay":
        return ReplayAgent(**kwargs)
    if name == "claude":
        from .claude import ClaudeAgent  # optional dependency
        return ClaudeAgent(**kwargs)
    raise ValueError(f"unknown agent '{name}' (choose 'replay' or 'claude')")
