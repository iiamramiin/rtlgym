# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Resource-limited wrappers around the EDA tools.

Every tool runs in its own process session with a wall-clock timeout, CPU,
memory, and file-size limits, a minimal environment (no API keys or other
secrets), and output captured to a size-capped file, inside a throwaway working
directory. Candidate RTL is untrusted input: a policy can emit infinite loops,
huge memories, endless $display output, or system tasks that touch the file
system, so nothing here trusts it. This is not a hardened sandbox: there is no
container, syscall filter, or network isolation.
"""

from __future__ import annotations

import json
import os
import re
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
FILE_LIMIT_BYTES = 256 * 1024**2      # any single file a tool writes, including its log
CAPTURE_TAIL_BYTES = 1024**2          # how much of a tool's output is kept in memory
REQUIRED_TOOLS = ("iverilog", "verilator", "yosys")

# Only these variables reach tool processes. Everything else, including API keys
# and tokens in the parent environment, is dropped.
_SAFE_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR", "USER",
                  "LOGNAME", "VIRTUAL_ENV")

# Sets limits in a fresh interpreter, then replaces itself with the tool. Used only
# when the util-linux `prlimit` binary is missing. Avoids preexec_fn, which is not
# safe to use from threads.
_LAUNCHER = (
    "import os, resource, sys\n"
    "cpu, mem, fsz = (int(x) for x in sys.argv[1:4])\n"
    "resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))\n"
    "resource.setrlimit(resource.RLIMIT_AS, (mem, mem))\n"
    "resource.setrlimit(resource.RLIMIT_FSIZE, (fsz, fsz))\n"
    "os.execvp(sys.argv[4], sys.argv[4:])\n"
)


class MissingToolError(RuntimeError):
    """An EDA tool is not installed: an infrastructure problem, never a candidate's fault."""


_TOOLS_CHECKED = False


def require_tools() -> None:
    global _TOOLS_CHECKED
    if _TOOLS_CHECKED:
        return
    missing = [t for t in REQUIRED_TOOLS if shutil.which(t) is None]
    if missing:
        raise MissingToolError(f"missing EDA tools: {', '.join(missing)} "
                               "(on Ubuntu: sudo apt-get install iverilog verilator yosys)")
    _TOOLS_CHECKED = True


def tool_env(extra: dict | None = None) -> dict:
    env = {k: os.environ[k] for k in _SAFE_ENV_KEYS if k in os.environ}
    env.setdefault("PATH", os.defpath)
    if extra:
        env.update(extra)
    return env


def _limited(cmd: list[str]) -> list[str]:
    if shutil.which("prlimit"):
        return ["prlimit", f"--cpu={CPU_LIMIT_S}", f"--as={MEM_LIMIT_BYTES}",
                f"--fsize={FILE_LIMIT_BYTES}", "--", *cmd]
    return [sys.executable, "-c", _LAUNCHER, str(CPU_LIMIT_S), str(MEM_LIMIT_BYTES),
            str(FILE_LIMIT_BYTES), *cmd]


@dataclass
class ToolRun:
    ok: bool
    returncode: int | None
    log: str
    elapsed_s: float
    timed_out: bool = False


def _read_tail(path: Path, n: int = CAPTURE_TAIL_BYTES) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - n))
            data = f.read()
    except OSError:
        return ""
    text = data.decode(errors="replace")
    return ("...[output truncated]\n" + text) if size > n else text


def run(cmd: list[str], cwd: Path, timeout_s: float, env: dict | None = None) -> ToolRun:
    """Run a tool in its own session; on timeout, kill the whole process group.

    Killing only the direct child is not enough: cocotb's runner spawns the
    simulator as a grandchild, which would keep spinning after a timeout. Output
    goes to a file in the working directory, so a design that prints without end
    cannot exhaust this process's memory; only the tail is read back.
    """
    t0 = time.monotonic()
    if shutil.which(cmd[0]) is None and not Path(cmd[0]).is_file():
        return ToolRun(False, None, f"tool not found: {cmd[0]}", time.monotonic() - t0)
    cwd.mkdir(parents=True, exist_ok=True)
    out_path = cwd / f".{Path(cmd[0]).name}.{os.getpid()}.{time.monotonic_ns()}.out"
    with open(out_path, "wb") as out:
        try:
            proc = subprocess.Popen(_limited(cmd), cwd=cwd, env=env or tool_env(), stdout=out,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        except FileNotFoundError as exc:
            return ToolRun(False, None, f"tool not found: {exc}", time.monotonic() - t0)
        timed_out = False
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(proc)
        finally:
            if proc.poll() is None:  # pragma: no cover - defensive
                _kill_group(proc)
    log = _read_tail(out_path)
    out_path.unlink(missing_ok=True)
    elapsed = time.monotonic() - t0
    if timed_out:
        return ToolRun(False, None, log + f"\n[timeout after {timeout_s:.0f}s]", elapsed,
                       timed_out=True)
    if proc.returncode == -signal.SIGXFSZ:
        log += f"\n[stopped: output exceeded {FILE_LIMIT_BYTES // 1024**2} MB]"
    return ToolRun(proc.returncode == 0, proc.returncode, log, elapsed)


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
    # Verilator exits non-zero on warnings under -Wall, so a non-zero exit with
    # warnings and no errors is still a clean run. Anything else that is not a clean
    # exit (tool missing, timeout, crash) is a failure, never free lint credit.
    ran = r.returncode is not None and not r.timed_out
    ok = ran and not real_errors and (r.returncode == 0 or bool(warnings))
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
    try:
        data = json.loads(stat.read_text())
        design = data.get("design") or next(iter(data.get("modules", {}).values()), {})
        types: dict[str, int] = design["num_cells_by_type"]
        cells = int(design["num_cells"])
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        res.log = tail(f"malformed synthesis statistics: {exc}\n" + r.log)
        return res
    res.cell_types = types
    res.cells = cells
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
    ok: bool                      # the worker exited cleanly and every expected test reported
    total: int = 0                # expected tests (from the testbench), not just reported ones
    passed: int = 0
    failures: dict[str, str] = field(default_factory=dict)
    complete: bool = False
    log: str = ""
    elapsed_s: float = 0.0
    timed_out: bool = False

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


_TEST_RE = re.compile(r"@cocotb\.test\b[^\n]*\n(?:\s*@[^\n]*\n)*\s*async\s+def\s+(\w+)")


def expected_tests(test_file: Path) -> list[str]:
    """Names of the cocotb tests a testbench defines, in file order."""
    return _TEST_RE.findall(test_file.read_text())


def account_tests(expected: list[str], reported: dict[str, str | None],
                  note: str = "did not run (simulation crashed or timed out)"
                  ) -> tuple[int, int, dict[str, str], bool]:
    """Score against the expected test list: a test that never reported counts as
    failed, so a crash or partial report can never look like a full pass.

    `reported` maps test name -> None (passed) or a failure message.
    """
    names = expected or list(reported)
    failures: dict[str, str] = {}
    passed = 0
    for name in names:
        if name not in reported:
            failures[name] = note
        elif reported[name] is None:
            passed += 1
        else:
            failures[name] = reported[name] or "failed"
    complete = bool(names) and all(n in reported for n in names)
    return len(names), passed, failures, complete


def simulate_cocotb(src: Path, top: str, test_file: Path, workdir: Path,
                    timeout_s: float = 60) -> SimResult:
    """Run the hidden cocotb testbench in a separate process with a hard timeout."""
    test_dir = workdir / "sim"
    test_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(test_file, test_dir / test_file.name)
    results = test_dir / "results.xml"
    results.unlink(missing_ok=True)          # never read a report from an earlier run
    cmd = [sys.executable, "-m", "rtlgym.simworker",
           "--src", str(src), "--top", top,
           "--test-dir", str(test_dir), "--test-module", test_file.stem,
           "--results", str(results)]
    env = tool_env({"PYTHONPATH": str(Path(__file__).resolve().parent.parent)})
    r = run(cmd, cwd=test_dir, timeout_s=timeout_s, env=env)
    reported = parse_junit(results) if results.is_file() else {}
    total, passed, failures, complete = account_tests(expected_tests(test_file), reported)
    return SimResult(ok=r.ok and complete, total=total, passed=passed, failures=failures,
                     complete=complete, log=tail(_clean_sim_log(r.log), 2000),
                     elapsed_s=r.elapsed_s, timed_out=r.timed_out)


_NOISE = ("gpi", "pygpi", "cocotb.initialize", "cocotb.regression", "Loaded entry", "VPI")


def _clean_sim_log(log: str) -> str:
    """Drop simulator start-up chatter so feedback shows only what matters."""
    keep = [ln for ln in log.splitlines() if not any(n in ln for n in _NOISE)]
    return "\n".join(keep).strip()


def _failure_message(el: ET.Element) -> str:
    """The failure text, across cocotb versions: 2.1 writes message="...";
    2.0.x writes error_msg="..." (and msg="..." for start-up failures).
    pytest's assertion introspection lines ("+  where 0 = <Model object at 0x7f...>.q")
    are dropped: they hold memory addresses (so results would differ run to run) and
    the testbench's internal names."""
    text = next((el.get(a) for a in ("message", "error_msg", "msg") if el.get(a)), None)
    if text is None:
        text = (el.text or "").strip() or "failed"
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("+")]
    return "\n".join(lines).strip() or "failed"


def parse_junit(path: Path) -> dict[str, str | None]:
    """Map each reported testcase to None (passed) or its failure message."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return {}
    out: dict[str, str | None] = {}
    for i, tc in enumerate(root.iter("testcase")):
        name = tc.get("name", f"test{i}")
        bad = tc.find("failure")
        if bad is None:
            bad = tc.find("error")
        if bad is not None:
            out[name] = _failure_message(bad).strip()[:500]
        elif tc.find("skipped") is not None:
            out[name] = "skipped"
        else:
            out[name] = None
    return out


def tool_versions() -> dict[str, str]:
    out = {}
    for name, cmd in {"iverilog": ["iverilog", "-V"], "yosys": ["yosys", "-V"],
                      "verilator": ["verilator", "--version"]}.items():
        try:
            out[name] = subprocess.run(cmd, capture_output=True, text=True,
                                       timeout=10).stdout.splitlines()[0].strip()
        except Exception:  # noqa: BLE001
            out[name] = "missing"
    # The test harness version matters too (e.g., its JUnit failure format).
    try:
        from importlib.metadata import version
        out["cocotb"] = version("cocotb")
    except Exception:  # noqa: BLE001
        out["cocotb"] = "missing"
    return out
