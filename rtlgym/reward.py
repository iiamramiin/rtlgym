# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Shaped reward for RTL generation.

The reward is a ladder: each rung is only reachable once the previous one holds,
so the policy cannot collect PPA reward for a design that is wrong, or lint
reward for code that does not compile.

    0.00  static check fails (forbidden constructs) or does not compile
    +0.10 compiles
    +0.05 lint clean (decays with warning count)
    +0.70 x fraction of hidden functional tests passed
    +0.15 area/depth bonus (Yosys generic-gate proxies, not signoff PPA), only
          when the design is accepted: every expected test ran and passed, it
          synthesizes without latches, its interface matches, and the formal check
          passed (or is disabled). Matching the reference earns 80% of the bonus;
          a reference-to-candidate ratio of 1.25 (20% fewer cells or levels) earns
          all of it. A missing metric earns nothing for its component.

Penalties: inferred latches (-0.05); a test escape, where every hidden test
passes but the formal check finds an input sequence on which the design differs
from the reference (-0.10). Designs that simulate but do not synthesize have
their functional credit halved: behavioral code that only works in simulation
is not a valid answer to a hardware spec.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .evaluator import EvalResult


@dataclass(frozen=True)
class RewardWeights:
    compile: float = 0.10
    lint: float = 0.05
    functional: float = 0.70
    ppa: float = 0.15
    latch_penalty: float = 0.05
    escape_penalty: float = 0.10      # all tests pass, formal check finds a difference
    lint_warning_scale: float = 5.0   # warnings at which lint credit reaches zero
    ppa_headroom: float = 1.25        # ratio vs reference that earns the full PPA bonus
    area_vs_depth: float = 0.7        # PPA mix: area (cells) vs logic depth


def ppa_score(cells: int, depth: int | None, ref_cells: int, ref_depth: int | None,
              w: RewardWeights) -> float:
    def ratio(ref: int | None, got: int | None) -> float:
        if got is None:
            return 0.0                    # unavailable metric: no credit, never full credit
        return min(w.ppa_headroom, ref / max(got, 1)) / w.ppa_headroom
    a = ratio(ref_cells, cells)
    d = ratio(ref_depth, depth) if ref_depth else a
    return w.area_vs_depth * a + (1 - w.area_vs_depth) * d


def compute_reward(r: EvalResult, w: RewardWeights | None = None) -> tuple[float, dict]:
    w = w or RewardWeights()
    b = {"compile": 0.0, "lint": 0.0, "functional": 0.0, "ppa": 0.0, "penalty": 0.0}
    if not r.static_ok or not r.compile_ok:
        return 0.0, b

    b["compile"] = w.compile
    n_warn = len(r.lint_warnings)
    if r.lint_ok:
        b["lint"] = w.lint * max(0.0, 1.0 - n_warn / w.lint_warning_scale)

    func = w.functional * r.pass_rate
    if not r.synth_ok:
        func *= 0.5
    b["functional"] = func

    if r.latches:
        b["penalty"] -= w.latch_penalty

    full_pass = r.tests_total > 0 and r.tests_passed == r.tests_total
    formal_status = getattr(r, "formal_status", "disabled")
    if full_pass and formal_status == "fail":
        b["penalty"] -= w.escape_penalty

    # The bonus needs an accepted design (same predicate that ends an episode).
    # A formal error or timeout, an incomplete simulation, or an interface mismatch
    # withholds it.
    if getattr(r, "accepted", False) and r.cells is not None and r.ref_cells:
        b["ppa"] = w.ppa * ppa_score(r.cells, r.depth, r.ref_cells, r.ref_depth, w)

    total = max(0.0, sum(b.values()))
    total = min(1.0, total)
    b = {k: round(v, 4) for k, v in b.items()}
    return round(total, 4) if not math.isnan(total) else 0.0, b
