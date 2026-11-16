# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

import math
import sys

import pytest

from rtlgym import formal, tools
from rtlgym.task import list_tasks, load_task


@pytest.mark.parametrize("launcher", ("prlimit", "python"))
def test_child_receives_cpu_limit_after_wall_deadline(monkeypatch, tmp_path, launcher):
    which = tools.shutil.which
    if launcher == "prlimit" and which("prlimit") is None:
        pytest.skip("prlimit is unavailable")
    if launcher == "python":
        monkeypatch.setattr(tools.shutil, "which", lambda name: None if name == "prlimit" else which(name))

    wall_s = 255.25
    command = [sys.executable, "-c", "import resource; print(*resource.getrlimit(resource.RLIMIT_CPU))"]
    result = tools.run(command, tmp_path, timeout_s=wall_s)
    assert result.ok, result.log
    assert tuple(map(int, result.log.split())) == (261, 261)


def test_short_tool_retains_cpu_floor():
    assert tools._cpu_limit_s(30) == 120


@pytest.mark.parametrize("wall_s", (0, -1, math.nan, math.inf, 295.001))
def test_invalid_deadlines_fail_before_creating_workdir(tmp_path, wall_s):
    work = tmp_path / "work"
    with pytest.raises(ValueError, match="tool wall timeout"):
        tools.run([sys.executable, "-c", "pass"], work, timeout_s=wall_s)
    assert not work.exists()


def test_all_configured_formal_deadlines_fit_cpu_bounds(monkeypatch, tmp_path):
    deadlines = []

    def capture_run(cmd, cwd, timeout_s):
        deadlines.append(timeout_s)
        return tools.ToolRun(True, 0, "no model found: SUCCESS", 0.01)

    monkeypatch.setattr(formal, "run", capture_run)
    for task_id in list_tasks():
        task = load_task(task_id)
        if not task.has_formal:
            continue
        deadlines.clear()
        result = formal.check_equivalence(task, task.ref_path, tmp_path / task_id)
        assert result.status == "pass"
        assert len(deadlines) == 1
        wall_s = deadlines[0]
        assert math.ceil(wall_s) + tools.CPU_GRACE_S <= tools._cpu_limit_s(wall_s) <= tools.MAX_CPU_LIMIT_S
