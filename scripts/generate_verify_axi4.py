# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Build and qualify the bounded AXI verification corpus without model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path

from rtlgym import load_task, verify
from rtlgym.formal import parse_trace
from rtlgym.tools import compile_iverilog, tool_versions
from rtlgym.verify_syntax import validate_checker
from scripts import generate_verify_mutants as common

HEADER = "// SPDX-License-Identifier: MIT\n// Copyright (c) 2026 Ramin Rajaei\n\n"
TASK_ID = "verify_axi4_burst_slave"
PARENT = "axi4_burst_slave"
PROFILE = {"depth": 8, "params": {"ADDR_W": 3, "ID_W": 1, "LEN_W": 1},
           "reset": "rst", "clock": "clk", "observe_extra_cycle": True, "fifo_dout": None,
           "max_grading_s": 60}


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n").rstrip() + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def header_and_ports(parent):
    text = parent.read_text()
    header = text[text.index("module axi4_burst_slave"):text.index("    localparam int WORDS")]
    import re
    names = re.findall(r"(?:input|output)\s+logic\s+(?:\[[^\]]+\]\s*)?(\w+)", header)
    outputs = set(re.findall(r"output\s+logic\s+(?:\[[^\]]+\]\s*)?(\w+)", header))
    return header, names, outputs


def wrapper(core, parent, throttle=0, bdelay=0, rdelay=0, idle_zero=0):
    header, names, outputs = header_and_ports(parent)
    widths = {"s_axi_awready": "", "s_axi_wready": "", "s_axi_arready": "",
              "s_axi_bid": "[ID_W-1:0] ", "s_axi_bresp": "[1:0] ", "s_axi_bvalid": "",
              "s_axi_rid": "[ID_W-1:0] ", "s_axi_rdata": "[31:0] ",
              "s_axi_rresp": "[1:0] ", "s_axi_rlast": "", "s_axi_rvalid": ""}
    lines = [header, "    logic phase, b_waited, r_waited;",
             f"    wire permit = !rst && ({int(throttle)} == 0 || phase);",
             f"    wire b_show = ({int(bdelay)} == 0 || b_waited);",
             f"    wire r_show = ({int(rdelay)} == 0 || r_waited);"]
    for name in sorted(outputs):
        lines.append(f"    wire {widths[name]}inner_{name};")
    lines += ["    wire core_bready = s_axi_bready && b_show;",
              "    wire core_rready = s_axi_rready && r_show;",
              "    always @(posedge clk) begin",
              "        if (rst) begin phase<=0; b_waited<=0; r_waited<=0; end",
              "        else begin",
              "            phase<=!phase;",
              "            if (!inner_s_axi_bvalid || core_bready) b_waited<=0; else b_waited<=1;",
              "            if (!inner_s_axi_rvalid || core_rready) r_waited<=0; else r_waited<=1;",
              "        end", "    end"]
    for name in sorted(outputs):
        if name in ("s_axi_awready", "s_axi_wready", "s_axi_arready"):
            value = f"inner_{name} && permit"
        elif name == "s_axi_bvalid":
            value = "inner_s_axi_bvalid && b_show"
        elif name == "s_axi_rvalid":
            value = "inner_s_axi_rvalid && r_show"
        elif idle_zero:
            channel = "b" if name.startswith("s_axi_b") else "r"
            value = f"s_axi_{channel}valid ? inner_{name} : '0"
        else:
            value = f"inner_{name}"
        lines.append(f"    assign {name} = {value};")
    bindings = []
    for name in names:
        if name in outputs:
            value = f"inner_{name}"
        elif name in ("s_axi_awvalid", "s_axi_wvalid", "s_axi_arvalid"):
            value = f"{name} && permit"
        elif name == "s_axi_bready":
            value = "core_bready"
        elif name == "s_axi_rready":
            value = "core_rready"
        else:
            value = name
        bindings.append(f".{name}({value})")
    lines += ["    axi4_core #(.ADDR_W(ADDR_W),.ID_W(ID_W),.LEN_W(LEN_W)) core (",
              "        " + ",\n        ".join(bindings) + ");", "endmodule"]
    return HEADER + "\n".join(lines) + "\n" + core.replace("module axi4_burst_slave", "module axi4_core", 1)


CHANGES = [
    ("ignore_strobes", "comparison", "if (s_axi_wstrb[lane])", "if (1'b1)"),
    ("write_other_word", "index_swap", "memory[write_word][8*lane +: 8]",
     "memory[write_word ^ 1'b1][8*lane +: 8]"),
    ("write_no_advance", "dropped_update", "write_word <= write_word + 1'b1;", "write_word <= write_word;"),
    ("read_no_advance", "dropped_update", "next_read_word <= s_axi_araddr[ADDR_W-1:2] + 1'b1;",
     "next_read_word <= s_axi_araddr[ADDR_W-1:2];"),
    ("ignore_bad_descriptor", "comparison", "size != 3'd2", "1'b0"),
    ("ignore_last_mismatch", "operator", "(write_bad || bad_last_seen || last_bad)", "(write_bad)"),
    ("write_wrong_id", "operator", "s_axi_bid <= write_id;", "s_axi_bid <= write_id ^ 1'b1;"),
    ("read_wrong_id", "operator", "s_axi_rid <= s_axi_arid;", "s_axi_rid <= s_axi_arid ^ 1'b1;"),
    ("last_one_early", "off_by_one", "read_rem == LEN_W'(1)", "read_rem == LEN_W'(0)"),
    ("read_drop_valid", "dropped_update", "s_axi_rvalid <= 1'b1;", "s_axi_rvalid <= 1'b0;"),
    ("write_drop_response", "dropped_update", "s_axi_bvalid <= 1'b1;", "s_axi_bvalid <= 1'b0;"),
    ("reset_memory_one", "reset", "memory[word_idx] <= '0;", "memory[word_idx] <= 32'd1;"),
]


def build(repo):
    root = repo / "tasks" / TASK_ID
    parent = repo / "tasks" / PARENT / "ref.sv"
    core = parent.read_text()
    write(root / "designs/ref.sv", wrapper(core, parent))
    goods = []
    for name, settings in (("good_throttled", (1,0,0,0)),
                           ("good_delayed", (0,1,1,0)),
                           ("good_throttled_zero_idle", (1,1,1,1))):
        path = root / "designs" / f"{name}.sv"
        write(path, wrapper(core, parent, *settings))
        goods.append({"path": path.relative_to(root).as_posix(), "sha256": digest(path),
                      "freedom": {"ready_throttle": settings[0], "b_delay": settings[1],
                                  "r_delay": settings[2], "zero_idle_payload": settings[3]}})
    mutants = []
    for name, family, before, after in CHANGES:
        if core.count(before) != 1:
            raise ValueError(f"mutation {name} has {core.count(before)} sites")
        path = root / "mutants" / f"{name}.sv"
        write(path, wrapper(core.replace(before, after), parent))
        mutants.append({"id": name, "path": path.relative_to(root).as_posix(), "sha256": digest(path),
                        "family": family, "origin": f"generated:{PARENT}/{name}",
                        "operator": {"before": before, "after": after}})
    manifest = {"schema_version": 1, "profile": PROFILE,
                "reference": {"path": "designs/ref.sv", "sha256": digest(root / "designs/ref.sv")},
                "correct_designs": goods, "mutants": mutants,
                "hand_checker_sha256": digest(root / "ref.sv")}
    write(root / "mutants.json", json.dumps(manifest, indent=2))
    return root, manifest



def lower(path, top, params, expected, work):
    work.mkdir(parents=True, exist_ok=True)
    if not compile_iverilog(path, top, work).ok:
        raise ValueError(f"Icarus cannot compile {path}")
    output, interface = work / "design.il", work / "interface.json"
    settings = " ".join(f"-set {k} {v}" for k,v in params.items())
    script = [f'read_verilog -sv "{path}"']
    if settings:
        script.append(f"chparam {settings} {top}")
    script += [f"hierarchy -check -top {top}", "proc", "flatten", "memory", "opt_clean", "check -assert",
               f'write_json "{interface}"', f'write_rtlil "{output}"']
    status, log, _ = common.run_yosys("\n".join(script), work)
    if status != "pass":
        raise ValueError(f"cannot lower {path}: {log[-1500:]}")
    actual = json.loads(interface.read_text())["modules"][top]["ports"]
    actual = {name: (item["direction"],len(item["bits"])) for name,item in actual.items()}
    if actual != expected:
        raise ValueError(f"interface mismatch in {path}: {actual}")
    return output

def qualify(repo, root, manifest):
    original_ports = common.ports
    try:
        return _qualify(repo, root, manifest)
    finally:
        common.ports = original_ports


def _qualify(repo, root, manifest):
    task = load_task(TASK_ID, repo / "tasks")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="axi_verify_qualification_") as temp:
        work = Path(temp)
        ports = verify._ports(task, root / "designs/ref.sv", work)
        common.ports = lambda _task: ports
        entries = [manifest["reference"], *manifest["correct_designs"], *manifest["mutants"]]
        lowered = {}
        for index, entry in enumerate(entries):
            lowered[entry["path"]] = lower(root / entry["path"], PARENT, PROFILE["params"],
                                                  ports, work / f"lower_{index}")
        checked = validate_checker(task.ref_path.read_text(), ports, work / "syntax", "clk", "rst")
        if not checked.valid:
            raise ValueError(checked.reason)
        checker = work / "checker.sv"
        checker.write_text(checked.source)
        for index, entry in enumerate(entries):
            proof = verify.prove_checker(task, root / entry["path"], checker, ports,
                                         work / f"contract_{index}")
            expected = "fail" if entry in manifest["mutants"] else "pass"
            if proof.status != expected:
                raise ValueError(f"contract {entry['path']}: {proof.status}, expected {expected}: "
                                 f"{proof.message}\n{proof.trace}")
            entry["contract_proof"] = {"status": proof.status, "seconds": round(proof.seconds,3)}
            if expected == "fail":
                entry["contract_witness"] = proof.trace
        for index, entry in enumerate(manifest["correct_designs"]):
            status, log, seconds = common.pair_check(PARENT, lowered[manifest["reference"]["path"]],
                                                    lowered[entry["path"]], manifest,
                                                    work / f"freedom_{index}")
            if status != "different":
                raise ValueError(f"correct timing variant does not differ: {entry['path']}: {status}")
            entry["freedom_witness"] = parse_trace(log)
            entry["freedom_difference_seconds"] = round(seconds,3)
        admitted = []
        for index, entry in enumerate(manifest["mutants"]):
            comparisons = [(manifest["reference"], "reference"), *[(old, old["id"]) for old in admitted]]
            for other, label in comparisons:
                status, log, seconds = common.pair_check(PARENT, lowered[other["path"]],
                                                        lowered[entry["path"]], manifest,
                                                        work / f"pair_{index}_{label}")
                if status != "different":
                    raise ValueError(f"{entry['id']} vs {label}: {status}: {log[-800:]}")
                if label == "reference":
                    entry["witness"] = parse_trace(log)
                    entry["difference_seconds"] = round(seconds,3)
            admitted.append(entry)
        manifest["qualification"] = {"native_compile_and_interface": True,
            "reference_difference": True, "pairwise_behavioral_deduplication": True,
            "hand_checker_contract_gate": True, "legal_timing_variants_checked": True,
            "excluded": [], "tools": tool_versions(), "seconds": round(time.monotonic()-started,3)}
        write(root / "mutants.json", json.dumps(manifest, indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()
    root, manifest = build(args.repo)
    if not args.build_only:
        qualify(args.repo, root, manifest)
    print(f"{TASK_ID}: {len(manifest['mutants'])} mutants, "
          f"{len(manifest['correct_designs'])+1} correct designs")


if __name__ == "__main__":
    main()
