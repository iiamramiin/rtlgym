from __future__ import annotations

from abc import ABC, abstractmethod


class Agent(ABC):
    """A policy maps an observation (spec + feedback) to an action (RTL text)."""

    def begin_episode(self, obs: dict) -> None:  # noqa: B027 - optional hook
        """Called once after env.reset()."""

    @abstractmethod
    def act(self, obs: dict) -> str:
        ...
