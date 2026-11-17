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
from copy import copy
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from pathlib import Path

from .checks import extract_code, repair_source
from .evaluator import EvalResult, evaluate
from .reward import RewardWeights
from .task import DEFAULT_TASKS_ROOT, Task, list_tasks, load_task

FEEDBACK_LEVELS = ("none", "summary", "full")


@dataclass
class EpisodeState:
    task: Task
    turn: int = 0
    best_score: float = 0.0
    done: bool = False
    history: list[EvalResult] = field(default_factory=list)
    starter_code: str | None = None
    starter_feedback: str = ""
    starter_score: float = 0.0


class RTLEnv:
    """
    Args:
        tasks_root: folder with task subfolders.
        max_turns: attempts per episode.
        reward_mode: "improvement" (reward = gain over best score so far; the
            episode return starts at zero for design and measures gain over the
            starter score for repair) or "score" (reward =
            score of the current attempt).
        feedback: "none" (single-shot eval), "summary" (pass/fail counts only),
            or "full" (tool logs and failing test names).
        stop_on_pass: end the episode once an attempt is accepted: every expected
            hidden test ran and passed, the design synthesizes without latches, its
            interface matches, and the formal check passed (or is disabled).
        use_formal: run the formal equivalence check (when the task defines one).
    """

    def __init__(self, tasks_root: Path | str = DEFAULT_TASKS_ROOT, max_turns: int = 3,
                 reward_mode: str = "improvement", feedback: str = "full",
                 stop_on_pass: bool = True, weights: RewardWeights | None = None,
                 use_cache: bool = True, use_formal: bool = True):
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")
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
        task = load_task(task_id, self.tasks_root)
        self.state = EpisodeState(task=task)
        starter = task.start_code
        if starter is not None:
            shown = repair_source(starter)
            grade = evaluate(task, shown, self.weights, use_cache=self.use_cache,
                             use_formal=self.use_formal)
            self.state.starter_code = shown
            self.state.starter_feedback = _starter_feedback(grade)
            self.state.starter_score = self.state.best_score = grade.score
        return self._obs(feedback=""), {"task_id": task_id}

    def step(self, action: str) -> tuple[dict, float, bool, bool, dict]:
        return self._apply_grade(*self._grade(action))

    def _grade(self, action: str) -> tuple[str, EvalResult, float]:
        if self.state is None:
            raise RuntimeError("call reset() before step()")
        st = self.state
        if st.done:
            raise RuntimeError("the episode is over; call reset() to start a new one")
        code = extract_code(action, st.task.top)
        t0 = time.monotonic()
        res = evaluate(st.task, code, self.weights, use_cache=self.use_cache,
                       use_formal=self.use_formal)
        return code, res, time.monotonic() - t0

    def _apply_grade(self, code: str, res: EvalResult, grade_s: float
                     ) -> tuple[dict, float, bool, bool, dict]:
        st = self.state
        assert st is not None and not st.done
        st.turn += 1
        st.history.append(res)

        if self.reward_mode == "improvement":
            reward = 0.0 if res.unchanged_starter else max(0.0, res.score - st.best_score)
        else:
            reward = res.score
        reward = round(reward, 4)
        if not res.unchanged_starter:
            st.best_score = max(st.best_score, res.score)

        solved = is_solved(res)
        terminated = self.stop_on_pass and solved
        truncated = not terminated and st.turn >= self.max_turns
        st.done = terminated or truncated
        info = {"eval": res, "score": res.score, "best_score": st.best_score, "turn": st.turn,
                "solved": solved, "grade_s": round(grade_s, 3), "code": code}
        if st.starter_code is not None:
            info["lines_changed"] = 0 if res.unchanged_starter else _lines_changed(st.starter_code, code)
        return self._obs(feedback=format_feedback(res, self.feedback)), reward, terminated, \
            truncated, info

    def _fork(self, feedback: str) -> RTLEnv:
        assert self.state is not None
        other = copy(self)
        other.feedback = feedback
        other.state = replace(self.state, history=self.state.history.copy())
        return other

    # ------------------------------------------------------------------ helpers
    def _obs(self, feedback: str) -> dict:
        st = self.state
        assert st is not None
        obs = {
            "task_id": st.task.id,
            "top": st.task.top,
            "spec": st.task.spec,
            "turn": st.turn,
            "turns_left": self.max_turns - st.turn,
            "feedback": feedback,
        }
        if st.starter_code is not None and st.turn == 0:
            obs.update(starter_code=st.starter_code, starter_feedback=st.starter_feedback)
        return obs


def _lines_changed(starter: str, code: str) -> int:
    matcher = SequenceMatcher(None, starter.splitlines(), repair_source(code).splitlines())
    return sum(max(a_end - a, b_end - b) for tag, a, a_end, b, b_end in matcher.get_opcodes()
               if tag != "equal")


def is_solved(r: EvalResult) -> bool:
    """Accepted hardware: see EvalResult.accepted. Formal errors and timeouts,
    incomplete simulations, synthesis failures, latches, and interface mismatches
    all count as not solved."""
    return r.accepted


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
    if "formal" in r.resource_failures:
        return [f"Formal: stopped by a resource limit ({r.resource_failures['formal']})."]
    if "formal" in r.frontend_errors:
        lines = ["Formal: the front end could not parse the design."]
        if level == "full":
            lines.append(r.formal_message)
        return lines
    if r.formal_status == "error":
        return [f"Formal: could not run ({r.formal_message})."]
    if r.formal_status == "timeout":
        return ["Formal: no result within the time limit."]
    return []


def _test_failure_lines(r: EvalResult) -> list[str]:
    return [f"  FAIL {name}: {msg.splitlines()[0][:300] if msg else ''}"
            for name, msg in r.test_failures.items()]


def _starter_feedback(r: EvalResult) -> str:
    tests = f"Hidden tests: {r.tests_passed}/{r.tests_total} passed"
    if r.sim_complete and r.test_failures:
        return "\n".join([tests, *_test_failure_lines(r)])
    if r.all_tests_pass and r.sim_complete:
        if r.formal_status == "disabled":
            return f"{tests}\nFormal checking is disabled."
        if lines := _formal_lines(r, "full"):
            return "\n".join([tests, *lines])
    return format_feedback(r)


def format_feedback(r: EvalResult, level: str = "full") -> str:
    if level == "none":
        return ""
    lines = [f"Score: {r.score:.3f}"]
    if r.unchanged_starter:
        lines.append("The starting RTL is unchanged.")
    if not r.static_ok:
        lines.append("Rejected before compilation:")
        lines += [f"  - {v}" for v in r.violations]
        return "\n".join(lines)
    if not r.compile_ok:
        lines.append("Compilation failed (Icarus Verilog, -g2012).")
        if level == "full":
            lines.append(r.compile_log.strip())
        return "\n".join(lines)

    if r.sim_frontend == "sv2v":
        lines.append("Simulation front end: Icarus compiled after sv2v conversion.")
    lines.append(f"Hidden tests: {r.tests_passed}/{r.tests_total} passed")
    if r.sim_timed_out:
        lines.append("  The simulation timed out (a loop that never ends or logic that never "
                     "settles); tests that did not finish count as failed.")
    elif not r.sim_complete:
        lines.append("  The simulation ended before every test reported; missing tests count "
                     "as failed.")
    if level == "full":
        lines += _test_failure_lines(r)
        if not r.sim_complete and not r.sim_timed_out and r.sim_log:
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
    if r.ppa_unavailable and r.synth_ok:
        lines.append(f"Synthesis: alternate netlist checked ({r.flops} flops, {r.latches} latches). "
                     f"PPA unavailable: {r.ppa_unavailable}.")
    elif r.synth_ok:
        lines.append(f"Synthesis: {r.cells} generic cells ({r.flops} flops, "
                     f"{r.latches} latches), logic depth {r.depth}; "
                     f"reference: {r.ref_cells} cells, depth {r.ref_depth}")
    else:
        if "synthesis" in r.resource_failures:
            lines.append(f"Synthesis: stopped by a resource limit ({r.resource_failures['synthesis']}).")
        elif "synthesis" in r.frontend_errors:
            lines.append("Synthesis: the front end could not parse the design.")
        else:
            lines.append("Synthesis failed (Yosys).")
        if level == "full":
            lines.append(r.synth_log[-1000:])
    return "\n".join(lines)
