# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Grade one RTL candidate against one task.

Pipeline (cheap stages gate expensive ones, so a broken candidate costs
milliseconds instead of a full simulation):

    static checks -> compile (iverilog) -> [lint | synth | hidden tests] in parallel

Results are cached by (task fingerprint, candidate hash, tool versions) so that
re-submitting the same code during RL rollouts never pays tool latency twice.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import tools
from .checks import static_check
from .reward import RewardWeights, compute_reward
from .task import Task

CACHE_DIR = Path(os.environ.get("RTLGYM_CACHE", Path.home() / ".cache" / "rtlgym"))
_TOOL_VERSIONS: dict[str, str] | None = None
_REF_LOCK = threading.Lock()
_REF_PPA: dict[str, dict] = {}


@dataclass
class EvalResult:
    task_id: str
    code_sha: str
    static_ok: bool = False
    violations: list[str] = field(default_factory=list)
    compile_ok: bool = False
    compile_log: str = ""
    lint_ok: bool = False
    lint_warnings: list[str] = field(default_factory=list)
    lint_log: str = ""
    synth_ok: bool = False
    cells: int | None = None
    flops: int | None = None
    latches: int | None = None
    depth: int | None = None
    synth_log: str = ""
    interface_errors: list[str] = field(default_factory=list)
    tests_total: int = 0
    tests_passed: int = 0
    test_failures: dict[str, str] = field(default_factory=dict)
    sim_timed_out: bool = False
    sim_log: str = ""
    ref_cells: int | None = None
    ref_depth: int | None = None
    timings_s: dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)
    cached: bool = False

    @property
    def pass_rate(self) -> float:
        return self.tests_passed / self.tests_total if self.tests_total else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pass_rate"] = self.pass_rate
        return d


def _versions() -> dict[str, str]:
    global _TOOL_VERSIONS
    if _TOOL_VERSIONS is None:
        _TOOL_VERSIONS = tools.tool_versions()
    return _TOOL_VERSIONS


def reference_ppa(task: Task) -> dict:
    """Synthesize the reference once per process; it anchors the PPA reward."""
    with _REF_LOCK:
        if task.id in _REF_PPA:
            return _REF_PPA[task.id]
        with tempfile.TemporaryDirectory(prefix="rtlgym_ref_") as d:
            s = tools.synth_yosys(task.ref_path, task.top, Path(d))
        if not s.ok:
            raise RuntimeError(f"reference for {task.id} does not synthesize:\n{s.log}")
        _REF_PPA[task.id] = {"cells": s.cells, "depth": s.depth, "ports": s.ports}
        return _REF_PPA[task.id]


def _cache_key(task: Task, code: str, weights: RewardWeights) -> str:
    h = hashlib.sha256()
    h.update(task.fingerprint().encode())
    h.update(code.encode())
    h.update(json.dumps(_versions(), sort_keys=True).encode())
    h.update(json.dumps(asdict(weights), sort_keys=True).encode())
    return h.hexdigest()


def evaluate(task: Task, code: str, weights: RewardWeights | None = None,
             use_cache: bool = True, keep_dir: Path | None = None) -> EvalResult:
    weights = weights or RewardWeights()
    sha = hashlib.sha256(code.encode()).hexdigest()[:12]
    key = _cache_key(task, code, weights)
    cache_file = CACHE_DIR / f"{key}.json"
    if use_cache and cache_file.is_file():
        data = json.loads(cache_file.read_text())
        data.pop("pass_rate", None)
        res = EvalResult(**data)
        res.cached = True
        return res

    res = EvalResult(task_id=task.id, code_sha=sha)
    ref = reference_ppa(task)
    res.ref_cells, res.ref_depth = ref["cells"], ref["depth"]

    chk = static_check(code, task.top)
    res.static_ok, res.violations = chk.ok, chk.violations

    if res.static_ok:
        ctx = tempfile.TemporaryDirectory(prefix=f"rtlgym_{task.id}_") if keep_dir is None else None
        workdir = Path(ctx.name) if ctx else keep_dir
        workdir.mkdir(parents=True, exist_ok=True)
        try:
            _run_tools(task, code, workdir, res, ref)
        finally:
            if ctx:
                ctx.cleanup()

    res.score, res.breakdown = compute_reward(res, weights)
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(res.to_dict()))
    return res


def _run_tools(task: Task, code: str, workdir: Path, res: EvalResult, ref: dict) -> None:
    src = workdir / "candidate.sv"
    src.write_text(code)

    c = tools.compile_iverilog(src, task.top, workdir)
    res.compile_ok, res.compile_log = c.ok, tools.tail(c.log, 2000)
    res.timings_s["compile"] = round(c.elapsed_s, 3)
    if not res.compile_ok:
        return

    # Lint, synthesis and simulation are independent; run them concurrently so
    # wall-clock latency per step is max(), not sum(), of the three tools.
    (workdir / "lint").mkdir()
    (workdir / "synth").mkdir()
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_lint = pool.submit(tools.lint_verilator, src, task.top, workdir / "lint")
        f_syn = pool.submit(tools.synth_yosys, src, task.top, workdir / "synth")
        f_sim = pool.submit(tools.simulate_cocotb, src, task.top, task.test_path, workdir,
                            task.sim_timeout_s)
        lint, syn, sim = f_lint.result(), f_syn.result(), f_sim.result()

    res.lint_ok, res.lint_warnings, res.lint_log = lint.ok, lint.warnings, lint.log
    res.timings_s["lint"] = round(lint.elapsed_s, 3)

    res.synth_ok, res.synth_log = syn.ok, syn.log
    sim_only = sorted(set(lint.warnings) & tools.SIM_ONLY_CODES)
    if sim_only:
        # Yosys silently drops delays; Verilator does not. Treat as not synthesizable.
        res.synth_ok = False
        res.synth_log = (f"simulation-only constructs ({', '.join(sim_only)}): delays are "
                         "ignored by synthesis\n" + syn.log)
    res.cells, res.flops, res.latches, res.depth = syn.cells, syn.flops, syn.latches, syn.depth
    res.timings_s["synth"] = round(syn.elapsed_s, 3)
    if syn.ports:
        res.interface_errors = interface_diff(ref["ports"], syn.ports)

    res.tests_total, res.tests_passed = sim.total, sim.passed
    res.test_failures, res.sim_timed_out = sim.failures, sim.timed_out
    res.sim_log = sim.log if not sim.ok else ""
    res.timings_s["sim"] = round(sim.elapsed_s, 3)
    if not sim.ok and sim.total == 0:
        # Simulation crashed or timed out before any result: count all tests as failed.
        res.tests_total = max(res.tests_total, 1)


def interface_diff(expected: dict, got: dict) -> list[str]:
    errs = []
    for name, (direction, width) in expected.items():
        if name not in got:
            errs.append(f"missing port '{name}' ({direction}, {width} bits)")
        elif got[name] != (direction, width):
            errs.append(f"port '{name}' is {got[name][0]} [{got[name][1]} bits], "
                        f"expected {direction} [{width} bits]")
    for name in got:
        if name not in expected:
            errs.append(f"unexpected extra port '{name}'")
    return errs
