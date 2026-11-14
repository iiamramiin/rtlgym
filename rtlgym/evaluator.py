# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Grade one RTL candidate against one task.

Pipeline (cheap stages gate expensive ones, so a broken candidate costs
milliseconds instead of a full simulation):

    static checks -> compile (iverilog) -> [lint | synth | hidden tests | formal] in parallel

Results are cached by (grader version, task fingerprint, candidate hash, tool
versions, reward settings) so that re-submitting the same code during RL rollouts
never pays tool latency twice. Inconclusive results (a timeout or an incomplete
simulation) are never cached.

A candidate is **accepted** only when every expected hidden test ran and passed,
the design synthesizes without latches, its interface matches the reference, and
the formal check passed (or is disabled). The same predicate ends episodes,
defines solve rates, and gates the area/depth bonus.
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

from . import __version__, formal, tools
from .checks import static_check
from .reward import RewardWeights, compute_reward
from .task import Task

CACHE_DIR = Path(os.environ.get("RTLGYM_CACHE", Path.home() / ".cache" / "rtlgym"))
# Bump when grading semantics change, so cached results from older graders are ignored.
GRADER_VERSION = "4"
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
    sim_complete: bool = False
    sim_log: str = ""
    ref_cells: int | None = None
    ref_depth: int | None = None
    formal_status: str = "skipped"          # pass | fail | error | timeout | disabled | skipped
    formal_depth: int = 0
    formal_complete: bool = False
    formal_params: dict = field(default_factory=dict)
    formal_first_mismatch: int | None = None
    formal_counterexample: str = ""
    formal_message: str = ""
    timings_s: dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)
    cached: bool = False

    @property
    def pass_rate(self) -> float:
        return self.tests_passed / self.tests_total if self.tests_total else 0.0

    @property
    def all_tests_pass(self) -> bool:
        return self.tests_total > 0 and self.tests_passed == self.tests_total

    @property
    def test_escape(self) -> bool:
        """Every hidden test passes, yet the formal check found a real difference."""
        return self.all_tests_pass and self.formal_status == "fail"

    @property
    def inconclusive(self) -> bool:
        """The grader could not decide: a timeout, an incomplete simulation, or a
        formal error or timeout on a design that otherwise looks correct."""
        if not self.compile_ok:
            return False
        return (self.sim_timed_out or not self.sim_complete
                or (self.all_tests_pass and self.formal_status in ("error", "timeout")))

    @property
    def accepted(self) -> bool:
        """The single acceptance predicate: termination, solve rates, and the
        area/depth bonus all use it."""
        return (self.all_tests_pass and self.sim_complete and self.synth_ok
                and not self.latches and not self.interface_errors
                and self.formal_status in ("pass", "disabled"))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pass_rate"] = self.pass_rate
        d["accepted"] = self.accepted
        return d


def _versions() -> dict[str, str]:
    global _TOOL_VERSIONS
    if _TOOL_VERSIONS is None:
        _TOOL_VERSIONS = tools.tool_versions()
    return _TOOL_VERSIONS


def reference_ppa(task: Task) -> dict:
    """Synthesize the reference once per process (keyed by the task's content, not
    its name); it anchors the area/depth bonus and the interface check."""
    key = task.fingerprint()
    with _REF_LOCK:
        if key in _REF_PPA:
            return _REF_PPA[key]
        with tempfile.TemporaryDirectory(prefix="rtlgym_ref_") as d:
            s = tools.synth_yosys(task.ref_path, task.top, Path(d))
        if not s.ok or s.cells is None:
            raise RuntimeError(f"reference for {task.id} does not synthesize:\n{s.log}")
        _REF_PPA[key] = {"cells": s.cells, "depth": s.depth, "ports": s.ports}
        return _REF_PPA[key]


def _cache_key(task: Task, code: str, weights: RewardWeights, use_formal: bool) -> str:
    h = hashlib.sha256()
    h.update(f"grader={GRADER_VERSION};rtlgym={__version__};".encode())
    h.update(task.fingerprint().encode())
    h.update(code.encode())
    h.update(json.dumps(_versions(), sort_keys=True).encode())
    h.update(json.dumps(asdict(weights), sort_keys=True).encode())
    h.update(b"formal" if use_formal else b"no-formal")
    return h.hexdigest()


def evaluate(task: Task, code: str, weights: RewardWeights | None = None,
             use_cache: bool = True, keep_dir: Path | None = None,
             use_formal: bool = True) -> EvalResult:
    tools.require_tools()
    weights = weights or RewardWeights()
    sha = hashlib.sha256(code.encode()).hexdigest()[:12]
    key = _cache_key(task, code, weights, use_formal)
    cache_file = CACHE_DIR / f"{key}.json"
    if use_cache and keep_dir is None:
        cached = _load_cached(cache_file)
        if cached is not None:
            return cached

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
            _run_tools(task, code, workdir, res, ref, use_formal)
        finally:
            if ctx:
                ctx.cleanup()

    res.score, res.breakdown = compute_reward(res, weights)
    if use_cache and not res.inconclusive:
        _store_cached(cache_file, res)
    return res


def _load_cached(path: Path) -> EvalResult | None:
    try:
        data = json.loads(path.read_text())
        data.pop("pass_rate", None)
        data.pop("accepted", None)
        res = EvalResult(**data)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError):
        return None                      # damaged or outdated entry: grade again
    res.cached = True
    return res


def _store_cached(path: Path, res: EvalResult) -> None:
    """Write atomically, so a concurrent reader never sees a half-written file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(res.to_dict()))
        os.replace(tmp, path)
    except OSError:
        pass                             # the cache is an optimization, never required


def _run_tools(task: Task, code: str, workdir: Path, res: EvalResult, ref: dict,
               use_formal: bool = True) -> None:
    src = workdir / "candidate.sv"
    src.write_text(code)

    c = tools.compile_iverilog(src, task.top, workdir)
    res.compile_ok, res.compile_log = c.ok, tools.tail(c.log, 2000)
    res.timings_s["compile"] = round(c.elapsed_s, 3)
    if not res.compile_ok:
        return

    # Lint, synthesis, simulation and the formal check are independent; run them
    # concurrently so wall-clock latency per step is max(), not sum(), of the tools.
    (workdir / "lint").mkdir(exist_ok=True)
    (workdir / "synth").mkdir(exist_ok=True)
    run_formal = use_formal and task.has_formal
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_lint = pool.submit(tools.lint_verilator, src, task.top, workdir / "lint")
        f_syn = pool.submit(tools.synth_yosys, src, task.top, workdir / "synth")
        f_sim = pool.submit(tools.simulate_cocotb, src, task.top, task.test_path, workdir,
                            task.sim_timeout_s)
        f_fv = (pool.submit(formal.check_equivalence, task, src, workdir / "formal")
                if run_formal else None)
        lint, syn, sim = f_lint.result(), f_syn.result(), f_sim.result()
        fv = f_fv.result() if f_fv else None

    if fv is None:
        res.formal_status = "disabled"
    else:
        res.formal_status, res.formal_depth = fv.status, fv.depth
        res.formal_complete, res.formal_params = fv.complete, fv.params
        res.formal_first_mismatch, res.formal_message = fv.first_mismatch, fv.message
        res.formal_counterexample = formal.format_counterexample(fv)
        res.timings_s["formal"] = round(fv.elapsed_s, 3)

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
    res.sim_complete = sim.complete and not sim.timed_out
    res.sim_log = sim.log if not sim.ok else ""
    res.timings_s["sim"] = round(sim.elapsed_s, 3)


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
