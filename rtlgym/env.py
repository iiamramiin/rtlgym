# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Multi-turn, Gym-style environment.

Episode = one task. The observation is the spec plus feedback from the last
attempt (compiler errors, lint warnings, names of failing hidden tests, a formal
counterexample when the design differs from the reference, and synthesis
numbers). The action is a string containing SystemVerilog, optionally wrapped in
a markdown code fence.

step() returns the Gymnasium 5-tuple (obs, reward, terminated, truncated, info).
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from .checks import extract_code
from .evaluator import EvalResult, evaluate
from .reward import RewardWeights
from .task import DEFAULT_TASKS_ROOT, Task, list_tasks, load_task

FEEDBACK_LEVELS = ("none", "summary", "full")


@dataclass
class EpisodeState:
    task: Task
    turn: int = 0
    best_score: float = 0.0
    history: list[EvalResult] = field(default_factory=list)


class RTLEnv:
    """
    Args:
        tasks_root: folder with task subfolders.
        max_turns: attempts per episode.
        reward_mode: "improvement" (reward = gain over best score so far; the
            episode return equals the best score reached) or "score" (reward =
            score of the current attempt).
        feedback: "none" (single-shot eval), "summary" (pass/fail counts only),
            or "full" (tool logs and failing test names).
        stop_on_pass: end the episode once the attempt is solved: every hidden test
            passes and the formal check did not find a difference.
        use_formal: run the formal equivalence check (when the task defines one).
    """

    def __init__(self, tasks_root: Path | str = DEFAULT_TASKS_ROOT, max_turns: int = 3,
                 reward_mode: str = "improvement", feedback: str = "full",
                 stop_on_pass: bool = True, weights: RewardWeights | None = None,
                 use_cache: bool = True, use_formal: bool = True):
        if reward_mode not in ("improvement", "score"):
            raise ValueError("reward_mode must be 'improvement' or 'score'")
        if feedback not in FEEDBACK_LEVELS:
            raise ValueError(f"feedback must be one of {FEEDBACK_LEVELS}")
        self.tasks_root = Path(tasks_root)
        self.task_ids = list_tasks(self.tasks_root)
        self.max_turns = max_turns
        self.reward_mode = reward_mode
        self.feedback = feedback
        self.stop_on_pass = stop_on_pass
        self.weights = weights or RewardWeights()
        self.use_cache = use_cache
        self.use_formal = use_formal
        self.state: EpisodeState | None = None
        self._rng = random.Random()

    # ------------------------------------------------------------------ API
    def reset(self, task_id: str | None = None, seed: int | None = None) -> tuple[dict, dict]:
        if seed is not None:
            self._rng.seed(seed)
        task_id = task_id or self._rng.choice(self.task_ids)
        self.state = EpisodeState(task=load_task(task_id, self.tasks_root))
        return self._obs(feedback=""), {"task_id": task_id}

    def step(self, action: str) -> tuple[dict, float, bool, bool, dict]:
        if self.state is None:
            raise RuntimeError("call reset() before step()")
        st = self.state
        code = extract_code(action)
        t0 = time.monotonic()
        res = evaluate(st.task, code, self.weights, use_cache=self.use_cache,
                       use_formal=self.use_formal)
        grade_s = time.monotonic() - t0
        st.turn += 1
        st.history.append(res)

        if self.reward_mode == "improvement":
            reward = max(0.0, res.score - st.best_score)
        else:
            reward = res.score
        reward = round(reward, 4)
        st.best_score = max(st.best_score, res.score)

        solved = is_solved(res)
        terminated = self.stop_on_pass and solved
        truncated = not terminated and st.turn >= self.max_turns
        info = {"eval": res, "score": res.score, "best_score": st.best_score, "turn": st.turn,
                "solved": solved, "grade_s": round(grade_s, 3)}
        return self._obs(feedback=format_feedback(res, self.feedback)), reward, terminated, \
            truncated, info

    # ------------------------------------------------------------------ helpers
    def _obs(self, feedback: str) -> dict:
        st = self.state
        assert st is not None
        return {
            "task_id": st.task.id,
            "top": st.task.top,
            "spec": st.task.spec,
            "turn": st.turn,
            "turns_left": self.max_turns - st.turn,
            "feedback": feedback,
        }


def is_solved(r: EvalResult) -> bool:
    """Every hidden test passes and the formal check (if any) found no difference."""
    return r.all_tests_pass and r.formal_status != "fail"


def _formal_lines(r: EvalResult, level: str) -> list[str]:
    params = ", ".join(f"{k}={v}" for k, v in r.formal_params.items())
    note = f" (checked with {params})" if params else ""
    if r.formal_status == "pass":
        scope = ("for every input" if r.formal_complete
                 else f"for every input sequence up to {r.formal_depth} cycles after reset")
        return [f"Formal: equivalent to the reference {scope}{note}."]
    if r.formal_status == "fail":
        head = ("Formal: every hidden test passes, but the formal check found inputs where "
                "your design differs from the reference."
                if r.all_tests_pass else "Formal: not equivalent to the reference.")
        lines = [head]
        if level == "full" and r.formal_counterexample:
            lines.append(f"Counterexample{note}; reset is applied in cycle 1 and outputs are "
                         "compared from cycle 2:" if r.formal_depth > 1 else f"Counterexample{note}:")
            lines.append(r.formal_counterexample)
        return lines
    if r.formal_status == "error":
        return [f"Formal: could not run ({r.formal_message})."]
    if r.formal_status == "timeout":
        return ["Formal: no result within the time limit."]
    return []


def format_feedback(r: EvalResult, level: str = "full") -> str:
    if level == "none":
        return ""
    lines = [f"Score: {r.score:.3f}"]
    if not r.static_ok:
        lines.append("Rejected before compilation:")
        lines += [f"  - {v}" for v in r.violations]
        return "\n".join(lines)
    if not r.compile_ok:
        lines.append("Compilation failed (Icarus Verilog, -g2012).")
        if level == "full":
            lines.append(r.compile_log.strip())
        return "\n".join(lines)

    if r.sim_timed_out:
        lines.append("Hidden tests: simulation timed out (a loop that never ends or logic "
                     "that never settles); counted as failed")
    else:
        lines.append(f"Hidden tests: {r.tests_passed}/{r.tests_total} passed")
    if level == "full":
        for name, msg in r.test_failures.items():
            lines.append(f"  FAIL {name}: {msg.splitlines()[0][:300] if msg else ''}")
        if (r.tests_total and not r.test_failures and r.tests_passed < r.tests_total
                and not r.sim_timed_out):
            lines.append("  simulation log tail:\n" + r.sim_log[-1500:])
        if r.interface_errors:
            lines.append("Interface problems:")
            lines += [f"  - {e}" for e in r.interface_errors]
        if r.lint_warnings:
            lines.append(f"Lint: {len(r.lint_warnings)} Verilator warning(s): "
                         + ", ".join(sorted(set(r.lint_warnings))))
        elif r.lint_ok:
            lines.append("Lint: clean")
        else:
            lines.append("Lint failed:\n" + r.lint_log[-1000:])
    lines += _formal_lines(r, level)
    if r.synth_ok:
        lines.append(f"Synthesis: {r.cells} generic cells ({r.flops} flops, "
                     f"{r.latches} latches), logic depth {r.depth}; "
                     f"reference: {r.ref_cells} cells, depth {r.ref_depth}")
    else:
        lines.append("Synthesis failed (Yosys): the design is not synthesizable as written.")
        if level == "full":
            lines.append(r.synth_log[-1000:])
    return "\n".join(lines)
