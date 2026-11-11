# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Thin, sandboxed wrappers around the EDA tools.

Every tool runs in a subprocess with a wall-clock timeout and CPU/memory
limits, inside a throwaway working directory. Candidate RTL is untrusted input:
a policy can emit infinite loops, huge memories, or system tasks that touch the
file system, so nothing here trusts it.
"""

from __future__ import annotations

import json
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

MAX_LOG_CHARS = 4000
CPU_LIMIT_S = 120
MEM_LIMIT_BYTES = 2 * 1024**3


@dataclass
class ToolRun:
    ok: bool
    returncode: int | None
    log: str
    elapsed_s: float
    timed_out: bool = False


def _limit_resources() -> None:  # pragma: no cover - runs in the child process
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_S, CPU_LIMIT_S))
    resource.setrlimit(resource.RLIMIT_AS, (MEM_LIMIT_BYTES, MEM_LIMIT_BYTES))
    os.setsid()


def run(cmd: list[str], cwd: Path, timeout_s: float, env: dict | None = None) -> ToolRun:
    """Run a tool in its own process group; on timeout, kill the whole group.

    Killing only the direct child is not enough: cocotb's runner spawns the
    simulator as a grandchild, which would keep spinning after a timeout.
    """
    t0 = time.monotonic()
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace",
                                preexec_fn=_limit_resources)
    except FileNotFoundError as exc:
        return ToolRun(False, None, f"tool not found: {exc}", time.monotonic() - t0)
    try:
        out, _ = proc.communicate(timeout=timeout_s)
        return ToolRun(proc.returncode == 0, proc.returncode, out or "", time.monotonic() - t0)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        out, _ = proc.communicate()
        return ToolRun(False, None, (out or "") + f"\n[timeout after {timeout_s:.0f}s]",
                       time.monotonic() - t0, timed_out=True)
    finally:
        if proc.poll() is None:  # pragma: no cover - defensive
            _kill_group(proc)


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    proc.wait()


def tail(text: str, n: int = MAX_LOG_CHARS) -> str:
    return text if len(text) <= n else "...\n" + text[-n:]


# --------------------------------------------------------------------------- compile


def compile_iverilog(src: Path, top: str, workdir: Path, timeout_s: float = 30) -> ToolRun:
    return run(["iverilog", "-g2012", "-s", top, "-o", str(workdir / "compile_check.vvp"), str(src)],
               cwd=workdir, timeout_s=timeout_s)


# --------------------------------------------------------------------------- lint

_WARN_RE = re.compile(r"^%Warning-([A-Z0-9_]+):", re.M)
# Verilator codes that mean "this only works in a simulator", e.g. #delays.
SIM_ONLY_CODES = {"STMTDLY", "ASSIGNDLY", "INITIALDLY", "WAITCONST"}


@dataclass
class LintResult:
    ok: bool
    warnings: list[str]
    errors: int
    log: str
    elapsed_s: float


def lint_verilator(src: Path, top: str, workdir: Path, timeout_s: float = 30) -> LintResult:
    r = run(["verilator", "--lint-only", "-Wall", "--no-timing", "-Wno-DECLFILENAME", "-Wno-MULTITOP",
             "--top-module", top, str(src)], cwd=workdir, timeout_s=timeout_s)
    warnings = _WARN_RE.findall(r.log)
    real_errors = [ln for ln in r.log.splitlines()
                   if ln.startswith("%Error") and "Exiting due to" not in ln]
    # Verilator exits non-zero on warnings under -Wall; only real errors count as failure.
    ok = not r.timed_out and not real_errors
    errors = len(real_errors)
    return LintResult(ok, warnings, errors, tail(r.log), r.elapsed_s)


# --------------------------------------------------------------------------- synthesis

_LTP_RE = re.compile(r"Longest topological path in \S+ \(length=(\d+)\)")
GATE_LIB = "AND,NAND,OR,NOR,XOR,XNOR,ANDNOT,ORNOT,MUX"


@dataclass
class SynthResult:
    ok: bool
    cells: int | None = None
    flops: int | None = None
    latches: int | None = None
    depth: int | None = None
    ports: dict[str, tuple[str, int]] = field(default_factory=dict)
    cell_types: dict[str, int] = field(default_factory=dict)
    log: str = ""
    elapsed_s: float = 0.0


def synth_yosys(src: Path, top: str, workdir: Path, timeout_s: float = 60) -> SynthResult:
    """Generic-gate synthesis. Area proxy = gate count, delay proxy = logic depth."""
    iface = workdir / "iface.json"
    stat = workdir / "stat.json"
    ltp = workdir / "ltp.txt"
    script = "; ".join([
        f"read_verilog -sv {src}",
        f"hierarchy -check -top {top}",
        "proc",
        f"write_json {iface}",
        f"synth -flatten -top {top}",
        f"abc -g {GATE_LIB}",
        "opt_clean",
        f"tee -q -o {stat} stat -json",
        f"tee -q -o {ltp} ltp -noff",
    ])
    r = run(["yosys", "-q", "-p", script], cwd=workdir, timeout_s=timeout_s)
    res = SynthResult(ok=False, log=tail(r.log), elapsed_s=r.elapsed_s)
    if iface.is_file():
        res.ports = _ports_from_json(iface, top)
    if not r.ok or not stat.is_file():
        return res
    data = json.loads(stat.read_text())
    design = data.get("design") or next(iter(data.get("modules", {}).values()), {})
    types: dict[str, int] = design.get("num_cells_by_type", {})
    res.cell_types = types
    res.cells = int(design.get("num_cells", 0))
    res.flops = sum(n for t, n in types.items() if "DFF" in t.upper() or "SDFF" in t.upper())
    res.latches = sum(n for t, n in types.items() if "DLATCH" in t.upper())
    m = _LTP_RE.search(ltp.read_text()) if ltp.is_file() else None
    res.depth = int(m.group(1)) if m else None
    res.ok = True
    return res


def _ports_from_json(path: Path, top: str) -> dict[str, tuple[str, int]]:
    try:
        mod = json.loads(path.read_text())["modules"][top]
    except (KeyError, json.JSONDecodeError):
        return {}
    return {name: (p["direction"], len(p["bits"])) for name, p in mod.get("ports", {}).items()}


# --------------------------------------------------------------------------- simulation


@dataclass
class SimResult:
    ok: bool
    total: int = 0
    passed: int = 0
    failures: dict[str, str] = field(default_factory=dict)
    log: str = ""
    elapsed_s: float = 0.0
    timed_out: bool = False

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def simulate_cocotb(src: Path, top: str, test_file: Path, workdir: Path,
                    timeout_s: float = 60) -> SimResult:
    """Run the hidden cocotb testbench in a separate process with a hard timeout."""
    test_dir = workdir / "sim"
    test_dir.mkdir(exist_ok=True)
    shutil.copy(test_file, test_dir / test_file.name)
    results = test_dir / "results.xml"
    cmd = [sys.executable, "-m", "rtlgym.simworker",
           "--src", str(src), "--top", top,
           "--test-dir", str(test_dir), "--test-module", test_file.stem,
           "--results", str(results)]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(Path(__file__).resolve().parent.parent),
                                         env.get("PYTHONPATH", "")])
    r = run(cmd, cwd=test_dir, timeout_s=timeout_s, env=env)
    res = SimResult(ok=False, log=tail(_clean_sim_log(r.log), 2000), elapsed_s=r.elapsed_s,
                    timed_out=r.timed_out)
    if results.is_file():
        res.total, res.passed, res.failures = parse_junit(results)
        res.ok = res.total > 0
    return res


_NOISE = ("gpi", "pygpi", "cocotb.initialize", "cocotb.regression", "Loaded entry", "VPI")


def _clean_sim_log(log: str) -> str:
    """Drop simulator start-up chatter so feedback shows only what matters."""
    keep = [ln for ln in log.splitlines() if not any(n in ln for n in _NOISE)]
    return "\n".join(keep).strip()


def parse_junit(path: Path) -> tuple[int, int, dict[str, str]]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return 0, 0, {}
    total = passed = 0
    failures: dict[str, str] = {}
    for tc in root.iter("testcase"):
        total += 1
        bad = tc.find("failure")
        if bad is None:
            bad = tc.find("error")
        if bad is None and tc.find("skipped") is None:
            passed += 1
        elif bad is not None:
            msg = (bad.get("message") or bad.text or "failed").strip()
            failures[tc.get("name", f"test{total}")] = msg[:500]
    return total, passed, failures


def tool_versions() -> dict[str, str]:
    out = {}
    for name, cmd in {"iverilog": ["iverilog", "-V"], "yosys": ["yosys", "-V"],
                      "verilator": ["verilator", "--version"]}.items():
        try:
            out[name] = subprocess.run(cmd, capture_output=True, text=True,
                                       timeout=10).stdout.splitlines()[0].strip()
        except Exception:  # noqa: BLE001
            out[name] = "missing"
    return out
