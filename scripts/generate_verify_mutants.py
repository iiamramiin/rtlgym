# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Generate and independently qualify the first verification task corpora.

Run from a repository checkout with its pinned tools on PATH. Qualification is
uncached, rejects equivalent mutants, and checks the hand-written checker on
every correct design and every admitted mutant.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import tempfile
import time
import tomllib
from pathlib import Path

from rtlgym.formal import parse_trace
from rtlgym.tools import compile_iverilog, run, tool_versions

HEADER = "// SPDX-License-Identifier: MIT\n// Copyright (c) 2026 Ramin Rajaei\n\n"
TASKS = ("popcount16", "rr_arbiter4", "fifo_sync")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, code: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = code.replace("\r\n", "\n")
    if not text.startswith("// SPDX-License-Identifier: MIT"):
        text = HEADER + text
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def replace_once(code: str, old: str, new: str) -> str:
    if code.count(old) != 1:
        raise ValueError(f"expected one mutation site: {old!r}")
    return code.replace(old, new)


def generated(task: str, code: str) -> list[tuple[str, str, str]]:
    changes = []
    if task == "popcount16":
        output = "count = {1'b0, s3[0]} + {1'b0, s3[1]};"
        summation = "({1'b0, s3[0]} + {1'b0, s3[1]})"
        changes += [
            ("operator_xor", "operator", output, "count = {1'b0, s3[0]} ^ {1'b0, s3[1]};"),
            ("operator_or", "operator", output, "count = {1'b0, s3[0]} | {1'b0, s3[1]};"),
            ("offset_plus", "off_by_one", output, f"count = {summation} + 5'd1;"),
            ("offset_minus", "off_by_one", output, f"count = {summation} - 5'd1;"),
            ("threshold_eight", "comparison", output,
             f"count = ({summation} >= 5'd8) ? {summation} - 5'd1 : {summation};"),
            ("drop_bit_zero", "dropped_input", "x[2*i]", "((i == 0) ? 1'b0 : x[2*i])"),
            ("duplicate_bit_two", "index_swap", "x[2*i]", "x[(i == 0) ? 2 : 2*i]"),
            ("rare_zero", "comparison", output, f"count = (x == 0) ? 5'd1 : {summation};"),
            ("drop_bit_fifteen", "dropped_input", "x[2*i+1]", "((i == 7) ? 1'b0 : x[2*i+1])"),
            ("rare_all_ones", "comparison", output, f"count = (&x) ? 5'd0 : {summation};"),
        ]
    elif task == "rr_arbiter4":
        changes += [
            ("reset_priority_two", "reset", "last <= 2'd3;", "last <= 2'd2;"),
            ("reset_grant_one", "reset", "gnt  <= '0;\n            last",
             "gnt  <= 4'b0001;\n            last"),
            ("pointer_plus_one", "off_by_one", "last <= pick;", "last <= pick + 2'd1;"),
            ("grant_index_plus_one", "index_swap", "4'b0001 << pick", "4'b0001 << 2'(pick + 2'd1)"),
            ("hold_idle_grant", "dropped_update", "end else begin\n            gnt  <= '0;",
             "end else begin\n            gnt  <= gnt;"),
            ("cursor_on_all_only", "dropped_update", "last <= pick;",
             "if (&req) last <= pick;"),
            ("reverse_priority", "operator", "for (int k = 4; k >= 1; k--)",
             "for (int k = 1; k <= 4; k++)"),
            ("skip_requester_three", "comparison", "if (req[2'(last + 2'(k))])",
             "if (req[2'(last + 2'(k))] && 2'(last + 2'(k)) != 2'd3)"),
            ("all_requests_only", "comparison", "end else if (any) begin", "end else if (&req) begin"),
            ("grant_two_bits", "operator", "4'b0001 << pick", "4'b0011 << pick"),
            ("idle_resets_priority", "reset", "gnt  <= '0;\n        end",
             "gnt  <= '0;\n            last <= 2'd3;\n        end"),
        ]
    else:
        changes += [
            ("full_one_late", "off_by_one", "count == (AW+1)'(DEPTH)", "count == (AW+1)'(DEPTH+1)"),
            ("empty_one_early", "off_by_one", "count == '0", "count == (AW+1)'(1)"),
            ("write_full_on_read", "comparison", "wr_en && !full", "wr_en && (!full || rd_en)"),
            ("read_empty_on_write", "comparison", "rd_en && !empty", "rd_en && (!empty || wr_en)"),
            ("drop_write_pointer", "dropped_update", "wptr      <= wptr + 1'b1;", "wptr <= wptr;"),
            ("drop_read_pointer", "dropped_update", "rptr <= rptr + 1'b1;", "rptr <= rptr;"),
            ("reset_count_one", "reset", "count <= '0;", "count <= (AW+1)'(1);"),
            ("swap_write_index", "index_swap", "mem[wptr] <= din;", "mem[wptr ^ AW'(1)] <= din;"),
            ("read_pointer_two", "off_by_one", "rptr <= rptr + 1'b1;", "rptr <= rptr + AW'(2);"),
            ("write_zero", "operator", "mem[wptr] <= din;", "mem[wptr] <= '0;"),
            ("write_msb_invert", "operator", "mem[wptr] <= din;", "mem[wptr] <= din ^ (W'(1) << (W-1));"),
            ("count_increment_on_read", "operator", "count <= count - 1'b1;", "count <= count + 1'b1;"),
        ]
    return [(name, family, replace_once(code, before, after)) for name, family, before, after in changes]


def fifo_freedom(code: str) -> dict[str, str]:
    old = "    localparam int AW = $clog2(DEPTH);"
    fragment = """    logic [W-1:0] registered_read;
    logic just_read;
    always @(posedge clk) begin
        if (rst)
            just_read <= 1'b0;
        else
            just_read <= do_rd;
    end
"""
    renamed = replace_once(code, "dout <= mem[rptr];", "registered_read <= mem[rptr];")
    renamed = renamed.replace(old, old + "\n" + fragment)
    return {
        "good_zero_idle": renamed.replace(
            "    assign full", "    assign dout = just_read ? registered_read : '0;\n    assign full", 1),
        "good_expose_idle": renamed.replace(
            "    assign full",
            "    assign dout = just_read ? registered_read : mem[rptr];\n    assign full", 1),
    }


def build_sources(source_root: Path, tasks_root: Path) -> list[tuple[Path, dict]]:
    built = []
    for task in TASKS:
        parent = source_root / "tasks" / task
        root = tasks_root / f"verify_{task}"
        meta = tomllib.loads((root / "task.toml").read_text())
        profile = meta["verification"]
        source = (parent / "ref.sv").read_text()
        write(root / "designs" / "ref.sv", source)
        correct = []
        for path in sorted((parent / "candidates").glob("good_*.sv")):
            output = root / "designs" / path.name
            write(output, path.read_text())
            correct.append({"path": output.relative_to(root).as_posix(), "sha256": digest(output)})
        if task == "fifo_sync":
            for name, code in fifo_freedom(source).items():
                output = root / "designs" / f"{name}.sv"
                write(output, code)
                correct.append({"path": output.relative_to(root).as_posix(), "sha256": digest(output)})
        mutants = []
        seeds = sorted(itertools.chain((parent / "candidates").glob("bug_*.sv"),
                                       (parent / "candidates").glob("escape_*.sv")))
        for path in seeds:
            output = root / "mutants" / path.name
            write(output, path.read_text())
            family = "comparison" if "full" in path.name or "width" in path.name else "behavioral"
            mutants.append({"id": path.stem, "path": output.relative_to(root).as_posix(),
                            "sha256": digest(output), "family": family,
                            "origin": f"parent:{task}/candidates/{path.name}"})
        for name, family, code in generated(task, source):
            output = root / "mutants" / f"{name}.sv"
            write(output, code)
            mutants.append({"id": name, "path": output.relative_to(root).as_posix(),
                            "sha256": digest(output), "family": family,
                            "origin": f"generated:{task}/{name}"})
        config = {"schema_version": 1, "profile": {
            "depth": profile["depth"], "params": profile.get("params", {}),
            "reset": profile.get("reset"), "clock": profile.get("clock"), "observe_extra_cycle": True,
            "fifo_dout": "read_only" if task == "fifo_sync" else None,
        }, "reference": {"path": "designs/ref.sv", "sha256": digest(root / "designs" / "ref.sv")},
            "correct_designs": correct, "mutants": mutants}
        built.append((root, config))
    return built


def ports(task: str) -> dict[str, tuple[str, int]]:
    if task == "popcount16":
        return {"x": ("input", 16), "count": ("output", 5)}
    if task == "rr_arbiter4":
        return {"clk": ("input", 1), "rst": ("input", 1), "req": ("input", 4), "gnt": ("output", 4)}
    return {"clk": ("input", 1), "rst": ("input", 1), "wr_en": ("input", 1), "din": ("input", 2),
            "rd_en": ("input", 1), "dout": ("output", 2), "full": ("output", 1),
            "empty": ("output", 1), "count": ("output", 3)}


def run_yosys(script: str, work: Path, deadline: int = 15) -> tuple[str, str, float]:
    work.mkdir(parents=True, exist_ok=True)
    path, logfile = work / "check.ys", work / "check.log"
    path.write_text(script)
    result = run(["yosys", "-q", "-l", str(logfile), "-s", str(path)], work, deadline + 5)
    log = logfile.read_text(errors="replace") if logfile.exists() else result.log
    if result.timed_out or "proof did time out" in log:
        return "timeout", log, result.elapsed_s
    if "model found: FAIL" in log or "proof did fail" in log:
        return "different", log, result.elapsed_s
    if result.ok:
        return "pass", log, result.elapsed_s
    return "error", log, result.elapsed_s


def lower(path: Path, top: str, params: dict, expected: dict, work: Path) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    if not compile_iverilog(path, top, work).ok:
        raise ValueError(f"Icarus cannot compile {path}")
    sets = " ".join(f"-set {k} {v}" for k, v in params.items())
    output, interface = work / "design.il", work / "interface.json"
    steps = [f'read_verilog -sv "{path}"', f"hierarchy -check -top {top}"]
    if sets:
        steps.append(f"chparam {sets} {top}")
    steps += ["proc", "flatten", "memory", "opt_clean", "check -assert",
              f"write_json {interface}", f"write_rtlil {output}"]
    status, log, _ = run_yosys("\n".join(steps), work)
    if status != "pass":
        raise ValueError(f"cannot lower {path}: {log[-1500:]}")
    actual = json.loads(interface.read_text())["modules"][top]["ports"]
    actual = {name: (value["direction"], len(value["bits"])) for name, value in actual.items()}
    if actual != expected:
        raise ValueError(f"interface mismatch in {path}: {actual}")
    return output


def wire(name: str, width: int) -> str:
    return f"wire [{width-1}:0] {name};"


def pair_harness(task: str) -> str:
    interface = ports(task)
    ins = [name for name, (direction, _) in interface.items() if direction == "input"]
    outs = [name for name, (direction, _) in interface.items() if direction == "output"]
    header = ", ".join(f"input [{interface[name][1]-1}:0] {name}" for name in ins)
    text = [f"module harness ({header});"]
    for prefix in ("gold", "gate"):
        text += [wire(f"{prefix}_{name}", interface[name][1]) for name in outs]
        bindings = [f".{name}({name})" for name in ins]
        bindings += [f".{name}({prefix}_{name})" for name in outs]
        text.append(f"{prefix} design_{prefix} ({', '.join(bindings)});")
    checks = [f"gold_{name} == gate_{name}" for name in outs if name != "dout"]
    if task == "fifo_sync":
        text += [
            "reg [2:0] expected_count;",
            "reg read_valid;",
            "wire take_rd = rd_en && expected_count != 0;",
            "wire take_wr = wr_en && expected_count < 4;",
            "always @(posedge clk) begin",
            "if (rst) begin expected_count <= 0; read_valid <= 0; end",
            "else begin",
            "read_valid <= take_rd;",
            "if (take_wr && !take_rd) expected_count <= expected_count + 1'b1;",
            "else if (take_rd && !take_wr) expected_count <= expected_count - 1'b1;",
            "end end",
        ]
        checks.append("(!read_valid || gold_dout == gate_dout)")
    text += [f"always @* assert ({' && '.join(checks)});", "endmodule"]
    return "\n".join(text)


def prove(script: list[str], config: dict, work: Path) -> tuple[str, str, float]:
    depth = config["profile"]["depth"]
    args = ["sat", "-verify", "-prove-asserts", "-show-inputs", "-show-outputs", "-timeout", "15"]
    if depth > 1:
        args += ["-seq", str(depth + 1), "-prove-skip", "1", "-set-at", "1", "rst", "1"]
        for step in range(2, depth + 2):
            args += ["-set-at", str(step), "rst", "0"]
    return run_yosys("\n".join([*script, " ".join(args + ["harness"])]), work)


def pair_check(task: str, first: Path, second: Path, config: dict, work: Path) -> tuple[str, str, float]:
    work.mkdir(parents=True, exist_ok=True)
    harness = work / "harness.sv"
    harness.write_text(pair_harness(task))
    script = []
    for source, name in ((first, "gold"), (second, "gate")):
        script += [f"read_rtlil {source}", f"rename {task} {name}",
                   f"design -stash {name}_stash"]
    script += ["design -copy-from gold_stash -as gold gold", "design -copy-from gate_stash -as gate gate",
               f"read_verilog -formal -sv {harness}", "hierarchy -check -top harness",
               "proc", "flatten", "memory", "opt_clean"]
    return prove(script, config, work)


def checker_check(task: str, design: Path, checker: Path, config: dict, work: Path) -> tuple[str, str, float]:
    work.mkdir(parents=True, exist_ok=True)
    interface = ports(task)
    ins = [name for name, (direction, _) in interface.items() if direction == "input"]
    outs = [name for name, (direction, _) in interface.items() if direction == "output"]
    header = ", ".join(f"input [{interface[name][1]-1}:0] {name}" for name in ins)
    body = [f"module harness ({header});"]
    body += [wire(name, interface[name][1]) for name in outs]
    bindings = ", ".join(f".{name}({name})" for name in interface)
    body += [f"{task} dut ({bindings});", f"rtl_checker monitor ({bindings});", "endmodule"]
    harness = work / "harness.sv"
    harness.write_text("\n".join(body))
    script = [f"read_rtlil {design}", f"read_verilog -formal -sv {checker}"]
    params = config["profile"]["params"]
    if params:
        sets = " ".join(f"-set {k} {v}" for k, v in params.items())
        script.append(f"chparam {sets} rtl_checker")
    script += [f"read_verilog -formal -sv {harness}", "hierarchy -check -top harness",
               "proc", "flatten", "memory", "opt_clean", "check -assert"]
    return prove(script, config, work)


def qualify(root: Path, config: dict, work: Path) -> dict:
    task = root.name.removeprefix("verify_")
    params = config["profile"]["params"]
    expected = ports(task)
    started = time.monotonic()
    reference = lower(root / config["reference"]["path"], task, params, expected, work / "ref")
    correct_checks = []
    for index, entry in enumerate(config["correct_designs"]):
        design = lower(root / entry["path"], task, params, expected, work / f"good_{index}")
        status, log, seconds = pair_check(task, reference, design, config, work / f"good_pair_{index}")
        if status != "pass":
            raise ValueError(f"correct design differs: {entry['path']} ({status})\n{log[-1000:]}")
        correct_checks.append({"path": entry["path"], "status": status, "seconds": round(seconds, 4)})
    unique = []
    pairs = []
    excluded = []
    for index, entry in enumerate(config["mutants"]):
        design = lower(root / entry["path"], task, params, expected, work / f"mutant_{index}")
        status, log, seconds = pair_check(task, reference, design, config, work / f"ref_mutant_{index}")
        if status != "different":
            excluded.append({"id": entry["id"], "reason": status})
            continue
        duplicate = None
        for prior, prior_design in unique:
            status, pair_log, pair_s = pair_check(task, prior_design, design, config,
                                                work / f"pair_{prior['id']}_{entry['id']}")
            pairs.append({"first": prior["id"], "second": entry["id"],
                          "status": status, "seconds": round(pair_s, 4)})
            if status == "pass":
                duplicate = prior["id"]
                break
            if status != "different":
                raise ValueError(f"mutant distinctness inconclusive: {prior['id']} / {entry['id']}")
        if duplicate:
            excluded.append({"id": entry["id"], "reason": f"equivalent:{duplicate}"})
            continue
        entry = dict(entry)
        entry["witness"] = parse_trace(log)
        entry["qualification_s"] = round(seconds, 4)
        unique.append((entry, design))
    if len(unique) < 10:
        raise ValueError(f"{root.name} has only {len(unique)} unique mutants; excluded {excluded}")

    checker = root / "ref.sv"
    hand_checks = []
    checker_designs = [(config["reference"], reference, "pass")]
    for index, entry in enumerate(config["correct_designs"]):
        checker_designs.append((entry, work / f"good_{index}" / "design.il", "pass"))
    checker_designs += [(entry, design, "different") for entry, design in unique]
    for index, (entry, design, expected_status) in enumerate(checker_designs):
        status, log, seconds = checker_check(task, design, checker, config, work / f"hand_{index}")
        if status != expected_status:
            raise ValueError(f"hand checker {entry['path']}: got {status}, "
                             f"expected {expected_status}\n{log[-1000:]}")
        hand_checks.append({"path": entry["path"], "status": status, "seconds": round(seconds, 4)})
    admitted = {entry["id"] for entry, _ in unique}
    for entry in config["mutants"]:
        if entry["id"] not in admitted:
            path = (root / entry["path"]).resolve()
            if path.parent != (root / "mutants").resolve():
                raise ValueError("excluded mutant is outside its task directory")
            path.unlink()
    config["mutants"] = [entry for entry, _ in unique]
    config["hand_checker_sha256"] = digest(checker)
    config["qualification"] = {"tool_versions": tool_versions(), "correct_design_checks": correct_checks,
                               "pairwise_checks": pairs, "hand_checker_checks": hand_checks,
                               "excluded": excluded, "seconds": round(time.monotonic() - started, 4)}
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tasks-root", type=Path, default=Path(__file__).resolve().parents[1] / "tasks")
    args = parser.parse_args()
    for root, config in build_sources(args.source_root.resolve(), args.tasks_root.resolve()):
        with tempfile.TemporaryDirectory(prefix=f"qualify_{root.name}_") as temporary:
            config = qualify(root, config, Path(temporary))
        (root / "mutants.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        print(root.name, len(config["mutants"]), config.get("qualification", {}).get("seconds"), flush=True)


if __name__ == "__main__":
    main()
