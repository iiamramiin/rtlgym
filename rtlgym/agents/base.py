# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

from __future__ import annotations

import copy
from abc import ABC, abstractmethod


class Agent(ABC):
    """A policy maps an observation (spec + feedback) to an action (RTL text)."""

    def begin_episode(self, obs: dict) -> None:  # noqa: B027 - optional hook
        """Called once after env.reset()."""

    @abstractmethod
    def act(self, obs: dict) -> str:
        ...

    def fork(self) -> Agent:
        """A copy that continues the current episode independently: the same
        conversation so far, separate from here on, with its own usage counters.
        Used to branch one first attempt into several feedback arms."""
        new = copy.copy(self)
        for name, value in vars(self).items():
            if isinstance(value, list):
                setattr(new, name, list(value))      # conversation, queues
        if isinstance(getattr(self, "usage", None), dict):
            new.usage = {k: type(v)() for k, v in self.usage.items()}
        return new
