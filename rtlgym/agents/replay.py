# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Offline agent that replays hand-written candidates.

Each task's task.toml lists a ``demo_trajectory`` (for example a buggy first
attempt followed by a fix). This lets the full multi-turn loop run in CI and on
a laptop with no API key, and gives a known-answer check on the reward.
"""

from __future__ import annotations

from pathlib import Path

from ..task import DEFAULT_TASKS_ROOT, load_task
from .base import Agent


class ReplayAgent(Agent):
    def __init__(self, tasks_root: Path | str = DEFAULT_TASKS_ROOT):
        self.tasks_root = Path(tasks_root)
        self._queue: list[Path] = []

    def begin_episode(self, obs: dict) -> None:
        task = load_task(obs["task_id"], self.tasks_root)
        names = task.demo_trajectory or tuple(p.name for p in task.candidates())
        self._queue = [task.candidates_dir / n for n in names]
        if not self._queue:
            self._queue = [task.ref_path]

    def act(self, obs: dict) -> str:
        path = self._queue.pop(0) if len(self._queue) > 1 else self._queue[0]
        return "```systemverilog\n" + path.read_text() + "```\n"
