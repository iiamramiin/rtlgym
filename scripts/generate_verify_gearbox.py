# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Rebuild and qualify the gearbox protocol-verification corpus, without model calls."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
import tomllib
from pathlib import Path

from rtlgym.formal import parse_trace
from rtlgym.tools import tool_versions
from scripts import generate_verify_mutants as corpus

TOP = "gearbox_16to12"
PORTS = {
    "clk": ("input", 1), "rst": ("input", 1), "in_valid": ("input", 1),
    "in_ready": ("output", 1), "in_data": ("input", 8), "out_valid": ("output", 1),
    "out_ready": ("input", 1), "out_data": ("output", 6),
}


def sources(root: Path, source_root: Path) -> dict:
    profile = tomllib.loads((root / "task.toml").read_text())["verification"]
    original = (source_root / "tasks" / TOP / "ref.sv").read_text()
    corpus.write(root / "designs" / "ref.sv", original)
    designs = []
    for name, throttle_in, throttle_out, idle in (
        ("good_bubble_input", True, False, "'0"),
        ("good_bubble_output", False, True, "in_data[3*UNIT_W-1:0]"),
        ("good_bubble_both", True, True, "pending[3*UNIT_W-1:0]"),
    ):
        extra = """    logic phase, held_offer;
    always @(posedge clk) begin
        if (rst) begin phase <= 0; held_offer <= 0; end
        else begin phase <= !phase; held_offer <= out_valid && !out_ready; end
    end
"""
        changed = corpus.replace_once(original, "    // Pending stream units",
                                      extra + "\n    // Pending stream units")
        if throttle_in:
            changed = corpus.replace_once(changed, "!rst && after_pop <= 4'd4",
                                          "!rst && after_pop <= 4'd4 && phase")
        if throttle_out:
            changed = corpus.replace_once(changed, "count >= 4'd3;",
                                          "count >= 4'd3 && (phase || held_offer);")
        changed = corpus.replace_once(changed, "pending[3*UNIT_W-1:0] : '0",
                                      f"pending[3*UNIT_W-1:0] : {idle}")
        output = root / "designs" / f"{name}.sv"
        corpus.write(output, changed)
        designs.append({"path": output.relative_to(root).as_posix(), "sha256": corpus.digest(output),
                        "freedom": {"input_bubbles": throttle_in, "output_bubbles": throttle_out,
                                    "inactive_output": idle}})
    changes = (
        ("valid_two", "comparison", "count >= 4'd3;", "count >= 4'd2;"),
        ("valid_four", "off_by_one", "count >= 4'd3;", "count >= 4'd4;"),
        ("ready_overflow", "comparison", "after_pop <= 4'd4;", "after_pop <= 4'd5;"),
        ("ready_underrun", "off_by_one", "after_pop <= 4'd4;", "after_pop <= 4'd3;"),
        ("swap_output_units", "index_swap", "pending[3*UNIT_W-1:0] : '0",
         "{pending[UNIT_W-1:0], pending[3*UNIT_W-1:UNIT_W]} : '0"),
        ("invert_output_bit", "operator", "pending[3*UNIT_W-1:0] : '0",
         "(pending[3*UNIT_W-1:0] ^ 1'b1) : '0"),
        ("input_bypass", "index_swap", "pending[3*UNIT_W-1:0] : '0", "in_data[3*UNIT_W-1:0] : '0"),
        ("pop_two", "off_by_one", "count - 4'd3", "count - 4'd2"),
        ("push_three", "off_by_one", "push ? 4'd4 : 4'd0", "push ? 4'd3 : 4'd0"),
        ("shift_two", "index_swap", "pending >> (3*UNIT_W)", "pending >> (2*UNIT_W)"),
        ("drop_push_data", "dropped_update", "remaining | (CAPACITY'(in_data) << (after_pop * UNIT_W))",
         "remaining"),
        ("drop_pop_data", "dropped_update", "pop ? pending >> (3*UNIT_W) : pending", "pending"),
        ("reset_count_one", "reset", "count <= '0;", "count <= 4'd1;"),
        ("ready_dependent_valid", "progress", "count >= 4'd3;", "count >= 4'd3 && out_ready;"),
    )
    mutants = []
    for name, family, before, after in changes:
        output = root / "mutants" / f"{name}.sv"
        corpus.write(output, corpus.replace_once(original, before, after))
        mutants.append({"id": name, "path": output.relative_to(root).as_posix(),
                        "sha256": corpus.digest(output), "family": family,
                        "origin": f"generated:{TOP}/{name}",
                        "operator": {"before": before, "after": after}})
    return {"schema_version": 1, "profile": {
        "depth": profile["depth"], "params": profile["params"], "reset": profile["reset"],
        "clock": profile["clock"], "observe_extra_cycle": True,
        "max_grading_s": profile["max_grading_s"],
    }, "reference": {"path": "designs/ref.sv", "sha256": corpus.digest(root / "designs" / "ref.sv")},
        "correct_designs": designs, "mutants": mutants}


def qualify(root: Path, config: dict, work: Path) -> dict:
    original_ports = corpus.ports
    try:
        return _qualify(root, config, work)
    finally:
        corpus.ports = original_ports


def _qualify(root: Path, config: dict, work: Path) -> dict:
    started = time.monotonic()
    # The common native compiler, bounded difference and pairwise checks use this
    # task's concrete profile. Correct variants are intentionally not equivalent.
    corpus.ports = lambda _task: PORTS
    lowered = {}
    all_entries = [config["reference"], *config["correct_designs"], *config["mutants"]]
    for index, entry in enumerate(all_entries):
        lowered[entry["path"]] = corpus.lower(root / entry["path"], TOP, config["profile"]["params"],
                                               PORTS, work / f"lower_{index}")
    reference = lowered[config["reference"]["path"]]
    checker = root / "ref.sv"
    correct_checks, freedom_checks = [], []
    for index, entry in enumerate([config["reference"], *config["correct_designs"]]):
        status, log, seconds = corpus.checker_check(TOP, lowered[entry["path"]], checker, config,
                                                   work / f"positive_{index}")
        if status != "pass":
            raise ValueError(f"correct design violates contract: {entry['path']} ({status})\n{log[-1500:]}")
        correct_checks.append({"path": entry["path"], "status": status, "seconds": round(seconds, 4)})
    # Legal variants must differ in handshake timing, not merely inactive data.
    corpus.ports = lambda _task: {name: value for name, value in PORTS.items() if name != "out_data"}
    try:
        for index, entry in enumerate(config["correct_designs"]):
            status, log, seconds = corpus.pair_check(TOP, reference, lowered[entry["path"]], config,
                                                    work / f"freedom_{index}")
            if status != "different":
                raise ValueError(f"correct variant does not exercise timing freedom: {entry['path']}")
            freedom_checks.append({"path": entry["path"], "status": status,
                                   "seconds": round(seconds, 4), "witness": parse_trace(log)})
    finally:
        corpus.ports = lambda _task: PORTS
    admitted, excluded, pairwise, hand = [], [], [], []
    for index, entry in enumerate(config["mutants"]):
        design = lowered[entry["path"]]
        status, log, seconds = corpus.checker_check(TOP, design, checker, config, work / f"hand_{index}")
        if status != "different":
            excluded.append({"id": entry["id"], "reason": f"contract:{status}"})
            continue
        hand.append({"path": entry["path"], "status": status, "seconds": round(seconds, 4),
                     "witness": parse_trace(log)})
        status, log, seconds = corpus.pair_check(TOP, reference, design, config, work / f"reference_{index}")
        if status != "different":
            raise ValueError(f"contract mutant must differ from reference: {entry['id']} ({status})")
        duplicate = None
        for prior in admitted:
            pair_status, _, pair_s = corpus.pair_check(TOP, lowered[prior["path"]], design, config,
                                                      work / f"pair_{prior['id']}_{entry['id']}")
            pairwise.append({"first": prior["id"], "second": entry["id"], "status": pair_status,
                             "seconds": round(pair_s, 4)})
            if pair_status == "pass":
                duplicate = prior["id"]
                break
            if pair_status != "different":
                raise ValueError(f"unresolved mutant pair {prior['id']} / {entry['id']}")
        if duplicate:
            excluded.append({"id": entry["id"], "reason": f"equivalent:{duplicate}"})
            continue
        admitted.append({**entry, "witness": parse_trace(log), "qualification_s": round(seconds, 4)})
    if len(admitted) < 10:
        raise ValueError(f"only {len(admitted)} qualified gearbox mutants: {excluded}")
    config["mutants"] = admitted
    config["hand_checker_sha256"] = corpus.digest(checker)
    config["qualification"] = {"tool_versions": tool_versions(), "correct_design_checks": correct_checks,
                               "timing_freedom_checks": freedom_checks,
                               "pairwise_checks": pairwise, "hand_checker_checks": hand,
                               "excluded": excluded, "seconds": round(time.monotonic() - started, 4)}
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve() / "tasks" / f"verify_{TOP}"
    config = sources(root, args.root.resolve())
    with tempfile.TemporaryDirectory(prefix="qualify_gearbox_") as temporary:
        config = qualify(root, config, Path(temporary))
    (root / "mutants.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    admitted = {entry["path"] for entry in config["mutants"]}
    for path in (root / "mutants").glob("*.sv"):
        if path.relative_to(root).as_posix() not in admitted:
            path.unlink()
    print(root.name, len(config["mutants"]), config["qualification"]["seconds"], flush=True)


if __name__ == "__main__":
    main()
