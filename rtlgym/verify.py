# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Bounded mutation grading of a port-only immediate assertion checker."""

from __future__ import annotations

import hashlib
import json
import secrets
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import formal, tools
from .checks import _FENCE_RE
from .evaluator import EvalResult
from .task import Task
from .verify_syntax import validate_checker

VERIFY_GRADER_VERSION = "3"


def extract_checker(action: str) -> str:
    """Keep the complete submitted artifact so validation sees extra modules."""
    blocks = list(_FENCE_RE.finditer(action))
    source = blocks[-1].group(2) if blocks else action
    return source.strip() + "\n"


@dataclass
class Proof:
    status: str
    seconds: float
    trace: str = ""
    message: str = ""


@dataclass
class Simulation:
    complete: bool
    failed: bool
    seconds: float
    trace: str = ""


def _artifact(root: Path, entry: dict) -> Path:
    path = root / entry["path"]
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("verification artifact is outside its task or missing")
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise ValueError(f"verification artifact hash mismatch: {entry['path']}")
    return path.resolve()


def load_manifest(task: Task) -> dict:
    root = task.verification_root
    path = root / task.verify.get("manifest", "mutants.json")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("verification manifest is outside its task")
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1 or not data.get("mutants"):
        raise ValueError("verification task needs a versioned, nonempty mutant manifest")
    entries = [data["reference"], *data["correct_designs"], *data["mutants"]]
    for entry in entries:
        _artifact(root, entry)
    hand_checker_hash = data.get("hand_checker_sha256")
    if (hand_checker_hash is not None
            and hashlib.sha256(task.ref_path.read_bytes()).hexdigest() != hand_checker_hash):
        raise ValueError("hand-written checker changed since corpus qualification")
    mutants = data["mutants"]
    if (len({m["id"] for m in mutants}) != len(mutants)
            or len({m["sha256"] for m in mutants}) != len(mutants)):
        raise ValueError("duplicate verification mutants")
    if any(not m.get("family") for m in mutants):
        raise ValueError("every mutant needs a family")
    profile = data["profile"]
    for name in ("depth", "params", "reset", "clock"):
        if profile.get(name) != task.verify.get(name):
            raise ValueError(f"manifest and task profile differ: {name}")
    if profile.get("observe_extra_cycle") is not True:
        raise ValueError("verification profiles require a final observation cycle")
    if profile.get("fifo_dout") != task.verify.get("fifo_dout"):
        raise ValueError("manifest and task FIFO output policy differ")
    return data


def _read_design(task: Task, source: Path) -> list[str]:
    commands = [f'read_verilog -sv "{source}"']
    params = task.verify.get("params", {})
    if params:
        settings = " ".join(f"-set {key} {int(value)}" for key, value in params.items())
        commands.append(f"chparam {settings} {task.dut_top}")
    commands.append(f"hierarchy -check -top {task.dut_top}")
    return commands


def _ports(task: Task, source: Path, workdir: Path) -> dict:
    interface = workdir / "interface.json"
    script = "; ".join([*_read_design(task, source), "proc", f'write_json "{interface}"'])
    result = tools.run(["yosys", "-Q", "-q", "-p", script], workdir, 15)
    if not result.ok or not interface.is_file():
        raise RuntimeError("verification reference interface cannot be elaborated: " + tools.tail(result.log))
    ports = tools._ports_from_json(interface, task.dut_top)
    if not ports or any(direction not in ("input", "output") for direction, _ in ports.values()):
        raise ValueError("verification DUT needs plain input and output ports")
    return ports


def _wire(direction: str, name: str, width: int) -> str:
    return f"{direction} [{width - 1}:0] {name}"


def _formal_wrapper(task: Task, ports: dict) -> str:
    declarations = [_wire(direction, name, width) for name, (direction, width) in ports.items()]
    connect = ", ".join(f".{name}({name})" for name in ports)
    return ("module __rtlgym_top(" + ", ".join(declarations) + ");\n"
            f"__rtlgym_dut dut({connect});\nrtl_checker observer({connect});\nendmodule\n")


def _trace(log: str, ports: dict) -> str:
    rows = []
    for step in formal.parse_trace(log):
        signals = step["signals"]
        values = ", ".join(f"{name}={signals[name]['hex']}" for name in ports if name in signals)
        if values:
            rows.append(f"cycle {step['step']}: {values}")
    return "\n".join(rows)


def prove_checker(task: Task, design: Path, checker: Path, ports: dict, workdir: Path) -> Proof:
    """Use native Yosys assertions, never the DUT's assertion-dropping converter."""
    workdir.mkdir(parents=True, exist_ok=True)
    wrapper = workdir / "wrapper.sv"
    wrapper.write_text(_formal_wrapper(task, ports))
    commands = [*_read_design(task, design), "proc", "flatten", "memory", "opt_clean",
                f"rename {task.dut_top} __rtlgym_dut", "design -stash dut_design",
                f'read_verilog -formal -sv "{checker}"', "hierarchy -check -top rtl_checker",
                "proc", "flatten", "memory", "opt_clean", "design -stash checker_design",
                "design -copy-from dut_design -as __rtlgym_dut __rtlgym_dut",
                "design -copy-from checker_design -as rtl_checker rtl_checker",
                f'read_verilog -formal -sv "{wrapper}"', "hierarchy -check -top __rtlgym_top",
                "prep -top __rtlgym_top -flatten", "async2sync", "opt_clean"]
    budget = float(task.verify.get("timeout_s", 15))
    depth = int(task.verify["depth"])
    sat = ["sat", "-prove-asserts", "-show-ports", "-timeout", str(int(budget))]
    if depth > 1:
        # One extra observation makes the final state transition visible to a
        # pre-NBA, rising-edge assertion. Initial DUT storage stays unconstrained.
        steps = depth + 1
        sat += ["-seq", str(steps)]
        if clock := task.verify.get("clock"):
            sat += ["-set", clock, "1"]
        reset = task.verify.get("reset")
        if reset:
            sat += ["-set-at", "1", reset, "1"]
            for cycle in range(2, steps + 1):
                sat += ["-set-at", str(cycle), reset, "0"]
    commands.append(" ".join([*sat, "__rtlgym_top"]))
    logfile = workdir / "formal.log"
    script = workdir / "formal.ys"
    script.write_text(";\n".join(commands))
    result = tools.run(["yosys", "-Q", "-q", "-l", str(logfile), "-s", str(script)],
                       workdir, budget + 5)
    log = logfile.read_text(errors="replace") if logfile.is_file() else result.log
    if result.ok and "no model found: SUCCESS" in log:
        return Proof("pass", result.elapsed_s)
    if result.ok and "model found: FAIL" in log:
        return Proof("fail", result.elapsed_s, _trace(log, ports))
    return Proof("inconclusive", result.elapsed_s, message=tools.tail(log, 1400))


def simulate_checker(task: Task, design: Path, checker: Path, ports: dict, workdir: Path) -> Simulation:
    """Collect trusted failure signals rather than Icarus's assertion exit code."""
    workdir.mkdir(parents=True, exist_ok=True)
    declarations = []
    initialize = []
    stimulus = []
    clock, reset = task.verify.get("clock"), task.verify.get("reset")
    for name, (direction, width) in ports.items():
        declarations.append(_wire("reg" if direction == "input" else "wire", name, width) + ";")
        if direction == "input":
            initialize.append(f"{name} = 0;")
            if name not in (clock, reset):
                stimulus.append(f"__seed = __seed * 1664525 + 1013904223; {name} = __seed;")
    token = secrets.token_hex(12)
    connections = ", ".join(f".{name}({name})" for name in ports)
    params = task.verify.get("params", {})
    settings = "#(" + ", ".join(f".{name}({int(v)})" for name, v in params.items()) + ")" if params else ""
    cycles = int(task.verify["depth"]) + 1 if clock else 64
    phase = [f"{clock} = 0;"] if clock else []
    if reset:
        phase.append(f"{reset} = (__cycle == 0);")
    phase.extend(stimulus)
    phase.append("#1;")
    if clock:
        phase += [f"{clock} = 1;", "#1;"]
    phase.append(f'if (__rtlgym_fail !== 1\'b0) $display("RTLGYM_FAIL_{token} %0d", __cycle);')
    values = " ".join(f"{name}=%h" for name in ports)
    phase.append(f'$display("RTLGYM_TRACE_{token} %0d {values}", __cycle, {", ".join(ports)});')
    phase.append("#1;")
    wrapper = workdir / "testbench.sv"
    wrapper.write_text("\n".join([
        "module __rtlgym_tb;", *declarations, "wire __rtlgym_fail;", "integer __cycle;",
        "reg [31:0] __seed;", f"{task.dut_top} {settings} dut({connections});",
        f"rtl_checker observer({connections}, .__rtlgym_fail(__rtlgym_fail));",
        "initial begin", "__seed = 12345;", *initialize,
        f"for (__cycle = 0; __cycle < {cycles}; __cycle = __cycle + 1) begin", *phase,
        "end", f'$display("RTLGYM_DONE_{token}");', "$finish;", "end", "endmodule",
    ]))
    binary = workdir / "simulation.vvp"
    compile_result = tools.run(["iverilog", "-g2012", "-s", "__rtlgym_tb", "-o", str(binary),
                                str(design), str(checker), str(wrapper)], workdir, 10)
    if not compile_result.ok:
        return Simulation(False, False, compile_result.elapsed_s, tools.tail(compile_result.log, 800))
    result = tools.run(["vvp", str(binary)], workdir, 5)
    complete = result.ok and f"RTLGYM_DONE_{token}" in result.log
    failed = f"RTLGYM_FAIL_{token}" in result.log
    return Simulation(complete, failed, result.elapsed_s + compile_result.elapsed_s,
                      tools.tail(result.log, 800))


def _cache_key(task: Task, code: str, manifest: dict) -> str:
    from .evaluator import _versions

    values = [VERIFY_GRADER_VERSION, task.fingerprint(), code, task.dut_top,
              json.dumps(task.verify, sort_keys=True), json.dumps(manifest, sort_keys=True),
              json.dumps(_versions(), sort_keys=True)]
    return hashlib.sha256("\0".join(values).encode()).hexdigest()


def evaluate_checker(task: Task, code: str, use_cache: bool = True,
                     keep_dir: Path | None = None) -> EvalResult:
    from . import evaluator

    tools.require_tools()
    started = time.monotonic()
    manifest = load_manifest(task)
    cache = evaluator.CACHE_DIR / f"verify-{_cache_key(task, code, manifest)}.json"
    if use_cache and keep_dir is None:
        if (cached := evaluator._load_cached(cache)) is not None:
            return cached
    res = EvalResult(task_id=task.id, code_sha=hashlib.sha256(code.encode()).hexdigest()[:12])
    detail = res.verification = {"status": "invalid", "mutants_total": len(manifest["mutants"]),
                                 "caught": 0, "weighted_caught": 0.0, "families": {},
                                 "assertions": 0, "state_bits": 0, "checker_bytes": len(code.encode()),
                                 "false_alarm_trace": "", "targets": []}
    context = tempfile.TemporaryDirectory(prefix="rtlgym_verify_") if keep_dir is None else None
    workdir = (Path(context.name) if context else Path(keep_dir)).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        with tools.runtime_budget(task.verify.get("max_grading_s")) as deadline:
            try:
                _evaluate(task, code, manifest, workdir, res)
            except RuntimeError:
                if deadline is None or time.monotonic() < deadline:
                    raise
                detail["status"] = "inconclusive"
                res.violations = ["Verification grading time limit exhausted"]
    finally:
        if context:
            context.cleanup()
    detail["grading_s"] = round(time.monotonic() - started, 3)
    res.timings_s["verify"] = detail["grading_s"]
    if use_cache and not res.inconclusive:
        evaluator._store_cached(cache, res)
    return res


def _evaluate(task: Task, code: str, manifest: dict, workdir: Path, res: EvalResult) -> None:
    detail = res.verification
    root = task.verification_root
    reference = _artifact(root, manifest["reference"])
    ports = _ports(task, reference, workdir)
    validated = validate_checker(code, ports, workdir / "syntax", task.verify.get("clock"),
                                 task.verify.get("reset"))
    detail.update(assertions=validated.assert_count, state_bits=validated.state_bits)
    if not validated.valid:
        if getattr(validated, "inconclusive", False):
            detail["status"] = "inconclusive"
        res.violations = [validated.reason]
        return
    res.static_ok = res.compile_ok = True
    source = workdir / "checker.sv"
    instrumented = workdir / "checker_sim.sv"
    source.write_text(validated.source)
    instrumented.write_text(validated.instrumented)
    positives = [manifest["reference"], *manifest["correct_designs"]]
    for index, entry in enumerate(positives):
        design = _artifact(root, entry)
        probe = simulate_checker(task, design, instrumented, ports, workdir / f"positive_{index}_sim")
        proof = prove_checker(task, design, source, ports, workdir / f"positive_{index}_formal")
        detail["targets"].append({"kind": "positive", "index": index, "formal": proof.status,
                                  "formal_message": proof.message,
                                  "formal_s": round(proof.seconds, 3), "sim_complete": probe.complete,
                                  "sim_failed": probe.failed, "sim_s": round(probe.seconds, 3),
                                  "simulation_trace": probe.trace})
        if proof.status == "fail":
            detail.update(status="false_alarm", false_alarm_trace=proof.trace)
            return
        if proof.status != "pass":
            detail["status"] = "inconclusive"
            return
    sizes = Counter(entry["family"] for entry in manifest["mutants"])
    families = {family: {"total": count, "caught": 0} for family, count in sorted(sizes.items())}
    detail["families"] = families
    for index, entry in enumerate(manifest["mutants"]):
        design = _artifact(root, entry)
        probe = simulate_checker(task, design, instrumented, ports, workdir / f"mutant_{index}_sim")
        proof = prove_checker(task, design, source, ports, workdir / f"mutant_{index}_formal")
        detail["targets"].append({"kind": "mutant", "id": entry["id"], "formal": proof.status,
                                  "formal_message": proof.message,
                                  "formal_s": round(proof.seconds, 3), "sim_complete": probe.complete,
                                  "sim_failed": probe.failed, "sim_s": round(probe.seconds, 3),
                                  "simulation_trace": probe.trace})
        if proof.status == "fail":
            detail["caught"] += 1
            families[entry["family"]]["caught"] += 1
        elif proof.status != "pass":
            detail["status"] = "inconclusive"
            return
    detail["weighted_caught"] = sum(group["caught"] / group["total"]
                                     for group in families.values()) / len(families)
    detail["status"] = "pass"
    res.score = round(detail["weighted_caught"], 4)
    res.breakdown = {"mutation": res.score}
    res.formal_status = "pass"
    res.tests_total, res.tests_passed = detail["mutants_total"], detail["caught"]
    res.sim_complete = True
