# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Regenerate and qualify the cache transaction verification profile."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import tempfile
import time
from pathlib import Path

from rtlgym import load_task, tools, verify
from rtlgym.formal import parse_trace
from rtlgym.verify_syntax import validate_checker
from scripts.generate_verify_mutants import lower, run_yosys

HEADER = "// SPDX-License-Identifier: MIT\n// Copyright (c) 2026 Ramin Rajaei\n\n"
DESIGN = r"""module cache_controller #(
    parameter integer DATA_W = 2,
    parameter integer TAG_W = 1,
    parameter integer INDEX_W = 1
) (
    input wire clk, rst, inv_valid,
    output wire inv_ready,
    input wire cpu_req_valid,
    output wire cpu_req_ready,
    input wire [TAG_W+INDEX_W:0] cpu_req_addr,
    output wire cpu_rsp_valid,
    input wire cpu_rsp_ready,
    output wire [DATA_W-1:0] cpu_rsp_data,
    output wire mem_req_valid,
    input wire mem_req_ready,
    output wire [TAG_W+INDEX_W-1:0] mem_req_addr,
    input wire mem_rsp_valid,
    output wire mem_rsp_ready,
    input wire [2*DATA_W-1:0] mem_rsp_data
);
    localparam integer HIT_DELAY = 0;
    localparam integer MISS_DELAY = 0;
    localparam integer REFILL_DELAY = 0;
    localparam integer REARM_DELAY = 0;
    localparam integer IDLE_PATTERN = 0;
    localparam integer LINES = 1 << INDEX_W;
    localparam [2:0] IDLE=0, START=1, SEND=2, REFILL=3, WAIT_RESPONSE=4, RESPONSE=5, REARM=6;
    reg [2:0] state;
    reg [1:0] delay_left;
    reg [LINES-1:0] valid;
    reg [TAG_W-1:0] tags [0:LINES-1];
    reg [2*DATA_W-1:0] words [0:LINES-1];
    reg [TAG_W+INDEX_W-1:0] pending_line;
    reg pending_offset;
    reg [DATA_W-1:0] result_word;
    wire [INDEX_W-1:0] req_index = cpu_req_addr[INDEX_W:1];
    wire [TAG_W-1:0] req_tag = cpu_req_addr[TAG_W+INDEX_W:INDEX_W+1];
    wire [INDEX_W-1:0] pending_index = pending_line[INDEX_W-1:0];
    wire hit = valid[req_index] && tags[req_index] == req_tag;
    wire [2*DATA_W-1:0] hit_line = words[req_index];

    assign inv_ready = !rst && state == IDLE;
    assign cpu_req_ready = inv_ready && !inv_valid;
    assign cpu_rsp_valid = !rst && state == RESPONSE;
    assign cpu_rsp_data = cpu_rsp_valid ? result_word : DATA_W'(IDLE_PATTERN);
    assign mem_req_valid = !rst && state == SEND;
    assign mem_req_addr = mem_req_valid ? pending_line : (TAG_W+INDEX_W)'(IDLE_PATTERN);
    assign mem_rsp_ready = !rst && state == REFILL;

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            delay_left <= 0;
            valid <= 0;
            pending_line <= 0;
            pending_offset <= 0;
            result_word <= 0;
            for (integer entry=0; entry<LINES; entry=entry+1) begin
                tags[entry] <= 0;
                words[entry] <= 0;
            end
        end else begin
            case (state)
                IDLE: begin
                    if (inv_valid) begin
                        valid <= 0;
                    end else if (cpu_req_valid) begin
                        if (hit) begin
                            result_word <=
                                cpu_req_addr[0] ? hit_line[2*DATA_W-1:DATA_W] : hit_line[DATA_W-1:0];
                            delay_left <= HIT_DELAY;
                            state <= HIT_DELAY == 0 ? RESPONSE : WAIT_RESPONSE;
                        end else begin
                            pending_line <= cpu_req_addr[TAG_W+INDEX_W:1];
                            pending_offset <= cpu_req_addr[0];
                            delay_left <= MISS_DELAY;
                            state <= MISS_DELAY == 0 ? SEND : START;
                        end
                    end
                end
                START: begin
                    if (delay_left == 1) state <= SEND;
                    else delay_left <= delay_left - 1'b1;
                end
                SEND: if (mem_req_ready) state <= REFILL;
                REFILL: if (mem_rsp_valid) begin
                    valid[pending_index] <= 1'b1;
                    tags[pending_index] <= pending_line[TAG_W+INDEX_W-1:INDEX_W];
                    words[pending_index] <= mem_rsp_data;
                    result_word <=
                        pending_offset ? mem_rsp_data[2*DATA_W-1:DATA_W] : mem_rsp_data[DATA_W-1:0];
                    delay_left <= REFILL_DELAY;
                    state <= REFILL_DELAY == 0 ? RESPONSE : WAIT_RESPONSE;
                end
                WAIT_RESPONSE: begin
                    if (delay_left == 1) state <= RESPONSE;
                    else delay_left <= delay_left - 1'b1;
                end
                RESPONSE: if (cpu_rsp_ready) state <= REARM_DELAY == 0 ? IDLE : REARM;
                REARM: state <= IDLE;
                default: state <= IDLE;
            endcase
        end
    end
endmodule
"""

CHANGES = [
    (
        "swap_hit_word",
        "index_swap",
        "cpu_req_addr[0] ? hit_line[2*DATA_W-1:DATA_W] : hit_line[DATA_W-1:0]",
        "cpu_req_addr[0] ? hit_line[DATA_W-1:0] : hit_line[2*DATA_W-1:DATA_W]",
    ),
    (
        "swap_refill_word",
        "index_swap",
        "pending_offset ? mem_rsp_data[2*DATA_W-1:DATA_W] : mem_rsp_data[DATA_W-1:0]",
        "pending_offset ? mem_rsp_data[DATA_W-1:0] : mem_rsp_data[2*DATA_W-1:DATA_W]",
    ),
    ("ignore_tag", "comparison", "valid[req_index] && tags[req_index] == req_tag", "valid[req_index]"),
    (
        "drop_invalidate",
        "dropped_update",
        "if (inv_valid) begin\n                        valid <= 0;",
        "if (inv_valid) begin\n                        valid <= valid;",
    ),
    (
        "wrong_refill_index",
        "index_swap",
        "words[pending_index] <= mem_rsp_data;",
        "words[pending_index ^ INDEX_W'(1)] <= mem_rsp_data;",
    ),
    (
        "wrong_request_address",
        "operator",
        "mem_req_valid ? pending_line :",
        "mem_req_valid ? pending_line ^ 1'b1 :",
    ),
    ("drop_response_hold", "comparison", "RESPONSE: if (cpu_rsp_ready)", "RESPONSE: if (1'b1)"),
    ("drop_request_hold", "comparison", "SEND: if (mem_req_ready)", "SEND: if (1'b1)"),
    ("busy_cpu_ready", "comparison", "inv_ready && !inv_valid", "!rst && !inv_valid"),
    ("drop_fill_valid", "dropped_update", "valid[pending_index] <= 1'b1;", "valid[pending_index] <= 1'b0;"),
    (
        "wrong_fill_tag",
        "operator",
        "tags[pending_index] <= pending_line[TAG_W+INDEX_W-1:INDEX_W];",
        "tags[pending_index] <= ~pending_line[TAG_W+INDEX_W-1:INDEX_W];",
    ),
    ("late_hit", "off_by_one", "integer HIT_DELAY = 0;", "integer HIT_DELAY = 3;"),
    ("late_miss_request", "off_by_one", "integer MISS_DELAY = 0;", "integer MISS_DELAY = 3;"),
    (
        "valid_on_reset",
        "reset",
        "valid <= 0;\n            pending_line",
        "valid <= '1;\n            pending_line",
    ),
]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n").rstrip() + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(root: Path) -> dict:
    write(root / "designs/ref.sv", HEADER + DESIGN)
    positives = []
    for name, settings in (
        ("good_hit_delay", {"HIT_DELAY": 1, "REFILL_DELAY": 1}),
        ("good_miss_delay", {"HIT_DELAY": 2, "MISS_DELAY": 2, "REFILL_DELAY": 2, "REARM_DELAY": 1}),
        ("good_independent_idle", {"HIT_DELAY": 2, "MISS_DELAY": 1, "IDLE_PATTERN": 3}),
    ):
        code = DESIGN
        for key, value in settings.items():
            code = code.replace(f"integer {key} = 0;", f"integer {key} = {value};")
        path = root / "designs" / f"{name}.sv"
        write(path, HEADER + code)
        positives.append(
            {"path": path.relative_to(root).as_posix(), "sha256": digest(path), "freedom": settings}
        )
    mutants = []
    for name, family, old, new in CHANGES:
        if DESIGN.count(old) != 1:
            raise ValueError(f"mutation site is not unique: {name}")
        path = root / "mutants" / f"{name}.sv"
        write(path, HEADER + DESIGN.replace(old, new))
        mutants.append(
            {
                "id": name,
                "path": path.relative_to(root).as_posix(),
                "sha256": digest(path),
                "family": family,
                "origin": f"generated:verify_cache_controller/designs/ref.sv#{name}",
                "operator": {"before": old, "after": new},
            }
        )
    return {
        "schema_version": 1,
        "profile": {
            "depth": 12,
            "params": {"DATA_W": 2, "TAG_W": 1, "INDEX_W": 1},
            "reset": "rst",
            "clock": "clk",
            "observe_extra_cycle": True,
            "max_grading_s": 60,
            "fifo_dout": None,
        },
        "reference": {"path": "designs/ref.sv", "sha256": digest(root / "designs/ref.sv")},
        "correct_designs": positives,
        "mutants": mutants,
    }


def pair_check(first: Path, second: Path, ports: dict, task, work: Path):
    work.mkdir(parents=True, exist_ok=True)
    inputs = {name: width for name, (direction, width) in ports.items() if direction == "input"}
    outputs = {name: width for name, (direction, width) in ports.items() if direction == "output"}
    text = [
        "module harness ("
        + ", ".join(f"input [{width - 1}:0] {name}" for name, width in inputs.items())
        + ");"
    ]
    for label in ("gold", "gate"):
        text += [f"wire [{width - 1}:0] {label}_{name};" for name, width in outputs.items()]
        bind = [f".{name}({name})" for name in inputs]
        bind += [f".{name}({label}_{name})" for name in outputs]
        text += [f"{label} dut_{label} ({', '.join(bind)});"]
    equal = " && ".join(f"gold_{name} == gate_{name}" for name in outputs)
    text += [f"always @* assert({equal});", "endmodule"]
    harness = work / "harness.sv"
    write(harness, "\n".join(text))
    commands = []
    for source, name in ((first, "gold"), (second, "gate")):
        commands += [f'read_rtlil "{source}"', f"rename {task.dut_top} {name}", f"design -stash {name}_stash"]
    commands += [
        "design -copy-from gold_stash -as gold gold",
        "design -copy-from gate_stash -as gate gate",
        f'read_verilog -formal -sv "{harness}"',
        "hierarchy -check -top harness",
        "proc",
        "flatten",
        "memory",
        "opt_clean",
    ]
    sat = [
        "sat",
        "-prove-asserts",
        "-show-inputs",
        "-show-outputs",
        "-timeout",
        "15",
        "-seq",
        str(task.verify["depth"] + 1),
        "-prove-skip",
        "1",
        "-set",
        "clk",
        "1",
        "-set-at",
        "1",
        "rst",
        "1",
    ]
    for cycle in range(2, task.verify["depth"] + 2):
        sat += ["-set-at", str(cycle), "rst", "0"]
    commands += [" ".join([*sat, "harness"])]
    return run_yosys(";\n".join(commands), work)


def qualify(task, config: dict, work: Path) -> dict:
    root = task.root
    started = time.monotonic()
    ports = verify._ports(task, root / config["reference"]["path"], work)
    checker = validate_checker(task.ref_path.read_text(), ports, work / "syntax", "clk", "rst")
    if not checker.valid:
        raise ValueError(checker.reason)
    regenerated = work / "checker.sv"
    write(regenerated, checker.source)
    lowered = {}
    checks = []
    entries = [config["reference"], *config["correct_designs"], *config["mutants"]]
    for index, entry in enumerate(entries):
        lowered[entry["path"]] = lower(
            root / entry["path"], task.dut_top, task.verify["params"], ports, work / f"lower_{index}"
        )
        proof = verify.prove_checker(
            task, root / entry["path"], regenerated, ports, work / f"contract_{index}"
        )
        expected = "fail" if "id" in entry else "pass"
        if proof.status != expected:
            raise ValueError(
                f"contract {entry['path']}: expected {expected}, got {proof.status}: "
                f"{proof.message}\n{proof.trace}"
            )
        checks.append({"path": entry["path"], "status": proof.status, "seconds": round(proof.seconds, 4)})
    reference = lowered[config["reference"]["path"]]
    freedom_checks = []
    for index, entry in enumerate(config["correct_designs"]):
        status, log, seconds = pair_check(
            reference, lowered[entry["path"]], ports, task, work / f"freedom_{index}"
        )
        if status != "different":
            raise ValueError(f"positive freedom is not observable: {entry['path']}: {status}")
        freedom_checks.append(
            {
                "path": entry["path"],
                "status": status,
                "seconds": round(seconds, 4),
                "witness": parse_trace(log),
            }
        )
    for entry in config["mutants"]:
        status, log, seconds = pair_check(
            reference, lowered[entry["path"]], ports, task, work / f"ref_{entry['id']}"
        )
        if status != "different":
            raise ValueError(f"mutant is not a proved bounded difference: {entry['id']}: {status}")
        entry["witness"] = parse_trace(log)
        entry["qualification_s"] = round(seconds, 4)
    pairs = []
    for first, second in itertools.combinations(config["mutants"], 2):
        status, _, seconds = pair_check(
            lowered[first["path"]],
            lowered[second["path"]],
            ports,
            task,
            work / f"pair_{first['id']}_{second['id']}",
        )
        if status != "different":
            raise ValueError(f"mutants are not distinct: {first['id']} / {second['id']}: {status}")
        pairs.append(
            {"first": first["id"], "second": second["id"], "status": status, "seconds": round(seconds, 4)}
        )
    config["hand_checker_sha256"] = digest(task.ref_path)
    config["qualification"] = {
        "tool_versions": tools.tool_versions(),
        "hand_checker_checks": checks,
        "correct_design_checks": freedom_checks,
        "pairwise_checks": pairs,
        "excluded": [],
        "seconds": round(time.monotonic() - started, 4),
        "method": "native compilation/interface; contract checker; "
        "bounded reference difference; pairwise bounded difference",
    }
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks-root", type=Path, default=Path(__file__).resolve().parents[1] / "tasks")
    parser.add_argument("--sources-only", action="store_true")
    args = parser.parse_args()
    root = args.tasks_root.resolve() / "verify_cache_controller"
    config = sources(root)
    write(root / "mutants.json", json.dumps(config, indent=2))
    if not args.sources_only:
        task = load_task(root.name, args.tasks_root)
        with tempfile.TemporaryDirectory(prefix="qualify_verify_cache_") as temporary:
            config = qualify(task, config, Path(temporary))
        write(root / "mutants.json", json.dumps(config, indent=2))
        print(root.name, len(config["mutants"]), config["qualification"]["seconds"], flush=True)


if __name__ == "__main__":
    main()
