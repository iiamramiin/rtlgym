# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Formal equivalence checking of a candidate against the reference design.

Tests sample behavior; a formal check covers every input sequence. The two
designs are combined into a miter (same inputs, outputs compared) and Yosys's
SAT solver searches for an input sequence that makes any output differ:

* Combinational designs are checked exhaustively (a complete proof).
* Sequential designs get a bounded model check: both designs start from the
  same all-zero state, reset is applied in cycle 1, and every input sequence of
  the configured length is covered. Reset is held low afterwards, so behavior
  under a mid-run reset is left to the simulation tests.

When the designs differ, the solver returns a counterexample: the exact inputs
per cycle and both designs' outputs. That trace is returned to the agent as
feedback, which is far more actionable than a failing test name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .task import Task
from .tools import run, tail

_ROW_RE = re.compile(r"^\s+(init|\d+)\s+\\(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$")
_COMB_ROW_RE = re.compile(r"^\s+\\(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$")  # no time column


@dataclass
class FormalResult:
    status: str                     # pass | fail | error | timeout
    depth: int = 0                  # cycles covered (1 for combinational designs)
    complete: bool = False          # True when the proof covers all behavior
    params: dict = field(default_factory=dict)
    first_mismatch: int | None = None
    trace: list[dict] = field(default_factory=list)
    message: str = ""
    log: str = ""
    elapsed_s: float = 0.0


def _script(task: Task, ref: Path, cand: Path, depth: int, timeout_s: float) -> str:
    cfg = task.formal
    top = task.top
    chparam = ""
    if cfg.get("params"):
        sets = " ".join(f"-set {k} {v}" for k, v in cfg["params"].items())
        chparam = f"chparam {sets} {top}"

    def load(src: Path, name: str) -> list[str]:
        lines = [f"read_verilog -sv {src}", f"hierarchy -check -top {top}"]
        if chparam:
            lines.append(chparam)
        lines += ["proc", "flatten", "memory", "opt_clean", f"rename {top} {name}",
                  f"design -stash {name}_design"]
        return lines

    lines = load(ref, "gold") + load(cand, "gate") + [
        "design -copy-from gold_design -as gold gold",
        "design -copy-from gate_design -as gate gate",
        "async2sync",
        "miter -equiv -flatten -make_assert -make_outputs gold gate miter",
        "hierarchy -top miter",
    ]
    sat = ["sat", "-verify", "-prove-asserts", "-show-inputs", "-show-outputs",
           "-timeout", str(int(timeout_s))]
    reset = cfg.get("reset")
    if depth > 1:
        sat += ["-set-init-zero", "-prove-skip", "1", "-seq", str(depth)]
        if reset:
            active = int(cfg.get("reset_active", 1))
            sat += ["-set-at", "1", f"in_{reset}", str(active)]
            for k in range(2, depth + 1):
                sat += ["-set-at", str(k), f"in_{reset}", str(1 - active)]
    lines.append(" ".join(sat + ["miter"]))
    return "\n".join(lines) + "\n"


def parse_trace(log: str) -> list[dict]:
    """Turn Yosys's counterexample table into one dict per time step."""
    steps: dict[int, dict] = {}
    for line in log.splitlines():
        m = _ROW_RE.match(line)
        if m:
            if m.group(1) == "init":
                continue
            t, name, dec, hexv, binv = int(m.group(1)), m.group(2), m.group(3), m.group(4), m.group(5)
        else:
            m = _COMB_ROW_RE.match(line)
            if not m:
                continue
            t, name, dec, hexv, binv = 1, m.group(1), m.group(2), m.group(3), m.group(4)
        steps.setdefault(t, {})[name] = {"dec": dec, "hex": hexv, "bin": binv}
    return [dict(step=t, **{"signals": steps[t]}) for t in sorted(steps)]


def first_mismatch(trace: list[dict]) -> int | None:
    for step in trace:
        trig = step["signals"].get("trigger")
        if trig and trig["dec"] == "1":
            return step["step"]
    return None


def check_equivalence(task: Task, cand: Path, workdir: Path, timeout_s: float = 60) -> FormalResult:
    cfg = task.formal
    depth = int(cfg.get("depth", 1))
    workdir.mkdir(parents=True, exist_ok=True)
    script = workdir / "equiv.ys"
    script.write_text(_script(task, task.ref_path, cand, depth, timeout_s))
    logfile = workdir / "equiv.log"
    # Read Yosys's own log file: stdout and stderr interleave unpredictably and can
    # split the counterexample table.
    r = run(["yosys", "-q", "-l", str(logfile), "-s", str(script)], cwd=workdir,
            timeout_s=timeout_s + 15)
    log = logfile.read_text(errors="replace") if logfile.is_file() else r.log
    res = FormalResult(status="error", depth=depth, complete=depth <= 1,
                       params=dict(cfg.get("params", {})), log=tail(log, 6000),
                       elapsed_s=r.elapsed_s)
    if r.timed_out or "proof did time out" in log:
        res.status, res.message = "timeout", f"no result within {timeout_s:.0f}s"
        return res
    if "no model found: SUCCESS" in log and r.ok:
        res.status = "pass"
        return res
    if "model found: FAIL" in log or "proof did fail" in log:
        res.status = "fail"
        res.trace = parse_trace(log)
        res.first_mismatch = first_mismatch(res.trace)
        return res
    err = next((ln for ln in log.splitlines() if ln.startswith("ERROR")), "")
    if "dlatch" in err:
        res.message = "the design infers latches, which the formal check does not support"
    else:
        res.message = err.replace("ERROR: ", "")[:300] or "Yosys could not build the equivalence check"
    return res


def _fmt(v: dict) -> str:
    b = v["bin"]
    if len(b) <= 1:
        return b
    return "0x" + v["hex"] if v["hex"] not in ("-", "x") else b


def format_counterexample(res: FormalResult, max_steps: int = 12) -> str:
    """Readable cycle-by-cycle table ending at the first mismatching cycle."""
    if not res.trace:
        return ""
    end = res.first_mismatch or res.trace[-1]["step"]
    rows = [s for s in res.trace if s["step"] <= end][-max_steps:]
    out = []
    for s in rows:
        sig = s["signals"]
        ins = ", ".join(f"{n[3:]}={_fmt(v)}" for n, v in sorted(sig.items())
                        if n.startswith("in_") and n not in ("in_clk",))
        outs = sorted(n[5:] for n in sig if n.startswith("gold_"))
        ref = ", ".join(f"{o}={_fmt(sig['gold_' + o])}" for o in outs if "gold_" + o in sig)
        got = ", ".join(f"{o}={_fmt(sig['gate_' + o])}" for o in outs if "gate_" + o in sig)
        mark = "   <-- differs" if s["step"] == res.first_mismatch else ""
        label = "  " if res.depth <= 1 else f"  cycle {s['step']:>2}: "
        out.append(f"{label}inputs[{ins}]  reference[{ref}]  yours[{got}]{mark}")
    return "\n".join(out)
