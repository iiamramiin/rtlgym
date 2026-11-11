# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Child-process entry point that builds and runs one cocotb testbench.

Kept separate so the parent can enforce a hard wall-clock timeout and never
shares interpreter state with a simulation of untrusted RTL.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--top", required=True)
    ap.add_argument("--test-dir", required=True)
    ap.add_argument("--test-module", required=True)
    ap.add_argument("--results", required=True)
    args = ap.parse_args()

    from cocotb_tools.runner import get_runner

    test_dir = Path(args.test_dir)
    build_dir = test_dir / "build"
    runner = get_runner("icarus")
    runner.build(
        sources=[Path(args.src)],
        hdl_toplevel=args.top,
        build_dir=build_dir,
        build_args=["-g2012"],
        timescale=("1ns", "1ps"),
        always=True,
    )
    runner.test(
        test_module=args.test_module,
        hdl_toplevel=args.top,
        build_dir=build_dir,
        test_dir=test_dir,
        results_xml=args.results,
        seed=12345,  # deterministic grading: same candidate, same reward
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
