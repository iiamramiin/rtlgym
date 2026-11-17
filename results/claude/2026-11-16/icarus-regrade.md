# Offline Icarus regrade

Regraded 17 unique task/source pairs from 21 archived arm turns. Each source is the exact saved RTL, deduplicated by grading task and its UTF-8 SHA-256. The original JSON and feedback are unchanged.

The offline regrade uses the guarded Icarus fallback in `bb101f2` (grader version 9), with three workers and no cache. WSL Ubuntu 24.04 supplies Icarus 12.0, Verilator 5.020, and Yosys 0.33 (`2584903a060`). The run also uses pinned sv2v v0.0.13 and cocotb 2.1.0. It makes no model calls.

The cohort covers every archived Icarus compile/elaboration rejection in the [November 14 design run](../2026-11-14/summary.md), November 16 design [Run A](run-a/summary.md) and [Run B](run-b/summary.md), and [repair Run 8](repair-pilot/summary.md). It also includes the recorded vvp internal assertion and one simulation timeout as a control. A simulation timeout alone does not establish an Icarus defect. A shared first attempt has an arm row in both archives.

| Archived classification | Archived arm turns | Distinct regraded sources |
| --- | ---: | ---: |
| Icarus runtime assertion | 2 | 1 |
| Icarus compile/elaboration failure | 18 | 15 |
| Simulation timeout control | 1 | 1 |

| Archived classification | Offline result | Unique sources |
| --- | --- | ---: |
| Icarus compile/elaboration failure | Accepted | 10 |
| Icarus compile/elaboration failure | Functional mismatch | 1 |
| Icarus compile/elaboration failure | Still rejected at compile | 1 |
| Icarus compile/elaboration failure | Tool resource limit | 3 |
| Simulation timeout control | Simulation timeout | 1 |
| Icarus runtime assertion | Incomplete simulation | 1 |

Of 15 historically rejected sources, 14 reached simulation through sv2v. 10 of those met the full acceptance rule. A successful translation only clears the simulator front end. The grader still checks behavior, synthesis, port shape and formal equivalence.

Verilator accepted 14/15 original submissions at lint. The Nov 14 router with an unpacked-array assignment-pattern initializer passes Verilator lint despite the older Icarus syntax diagnostic.

An initial probe accepted the AXI4 source after sv2v collapsed two identical assignments to `s_axi_bid`. The final fallback keeps Icarus's explicit multiple-driver rejection and does not translate that source. A separate uncached regrade of the same SHA confirmed 0/0 tests, skipped formal and a score of 0.

## Replay of saved attempts

Replace only the selected Icarus-cohort turn verdicts. All other turn verdicts are the ones recorded in their run files, including prior Yosys resource stops. The separate [router resource regrade](router-regrade.md) is excluded from these totals. Within-budget results ask whether any saved attempt was accepted under this substitution.

| Run | Model | Arm | Archived first → offline | Archived within budget → saved acceptance |
| --- | --- | --- | ---: | ---: |
| nov14 | haiku | full | 54/60 → 54/60 | 58/60 → 58/60 |
| nov14 | haiku | none | 54/60 → 54/60 | 54/60 → 56/60 |
| nov14 | sonnet | full | 50/60 → 50/60 | 60/60 → 60/60 |
| nov14 | sonnet | none | 50/60 → 50/60 | 57/60 → 58/60 |
| run-a | haiku | full | 58/60 → 59/60 | 60/60 → 60/60 |
| run-a | haiku | none | 58/60 → 59/60 | 58/60 → 59/60 |
| run-a | sonnet | full | 51/60 → 51/60 | 60/60 → 60/60 |
| run-a | sonnet | none | 51/60 → 51/60 | 56/60 → 56/60 |
| run-b | haiku | full | 16/21 → 16/21 | 20/21 → 20/21 |
| run-b | haiku | none | 16/21 → 16/21 | 18/21 → 18/21 |
| run-b | sonnet | full | 18/21 → 18/21 | 20/21 → 21/21 |
| run-b | sonnet | none | 18/21 → 18/21 | 19/21 → 19/21 |
| run8 | haiku | full | 7/8 → 7/8 | 7/8 → 7/8 |
| run8 | haiku | none | 7/8 → 7/8 | 8/8 → 8/8 |
| run8 | sonnet | full | 8/8 → 8/8 | 8/8 → 8/8 |
| run8 | sonnet | none | 8/8 → 8/8 | 8/8 → 8/8 |

Within the turn budget, paired acceptance changed as follows.

| Run | Both | Only full | Only plain | Neither |
| --- | ---: | ---: | ---: | ---: |
| Nov 14 | 111 → 113 | 7 → 5 | 0 → 1 | 2 → 1 |
| Run A | 114 → 115 | 6 → 5 | 0 → 0 | 0 → 0 |
| Run B | 36 → 37 | 4 → 4 | 1 → 0 | 1 → 1 |
| Run 8 repairs | 15 → 15 | 0 → 0 | 1 → 1 | 0 → 0 |

| Cohort | Archived failed first | Archived retry recoveries (full vs none) | Offline accepted first in that cohort | Accepted among saved attempts (full vs none) | Still fail first | Later saved acceptance (full vs none) among still-failed first |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Nov 14 | 16 | 14/16 vs 7/16 | 0 | 14/16 vs 10/16 | 16 | 14/16 vs 10/16 |
| Run A | 11 | 11/11 vs 5/11 | 1 | 11/11 vs 6/11 | 10 | 10/10 vs 5/10 |
| Run B | 8 | 6/8 vs 3/8 | 0 | 7/8 vs 3/8 | 8 | 7/8 vs 3/8 |
| Run A + B | 19 | 17/19 vs 8/19 | 1 | 18/19 vs 9/19 | 18 | 17/18 vs 8/18 |
| Run 8 repairs | 1 | 0/1 vs 1/1 | 0 | 0/1 vs 1/1 | 1 | 0/1 vs 1/1 |

The old grader determined which retries were sent and what those replies saw. A newly accepted first attempt would end its episode early. The results cannot establish how feedback would affect a fresh paired run on the revised grader.

## Archived turn mapping

Episode numbers are one-based positions in each model/arm JSON. Task-episode numbers are one-based within a task. SHA-256 values are shown with 12-character prefixes here.

| Run/model/arm | Episode / task episode / turn | Task | SHA-256 | Archived verdict | Offline outcome |
| --- | --- | --- | --- | --- | --- |
| [nov14/haiku/full](../2026-11-14/claude-haiku-5-5__full.json) | 34 / 4 / 1 | `noc_router5` | `b7cffabe597a` | 0/5 tests · error formal · 0.1500 · vvp: event.cc:596: virtual void vvp_fun_anyedge_sa::recv_vec4(vvp_net_ptr_t, const vvp_vector4_t&, vvp_context_t): Assertion `value' failed. | Incomplete simulation · 0/5 tests · error formal · 0.1500 · simulation via native · canonical synthesis stopped (memory allocation failure) |
| [nov14/haiku/none](../2026-11-14/claude-haiku-5-5__none.json) | 34 / 4 / 1 | `noc_router5` | `b7cffabe597a` | 0/5 tests · error formal · 0.1500 · vvp: event.cc:596: virtual void vvp_fun_anyedge_sa::recv_vec4(vvp_net_ptr_t, const vvp_vector4_t&, vvp_context_t): Assertion `value' failed. | Incomplete simulation · 0/5 tests · error formal · 0.1500 · simulation via native · canonical synthesis stopped (memory allocation failure) |
| [nov14/haiku/none](../2026-11-14/claude-haiku-5-5__none.json) | 32 / 2 / 2 | `noc_router5` | `05015c55e1eb` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:59: error: A reference to a wire or reg (`o') is not allowed in a constant expression. | Accepted · 5/5 tests · pass formal · 0.9222 · simulation via sv2v |
| [nov14/haiku/none](../2026-11-14/claude-haiku-5-5__none.json) | 32 / 2 / 3 | `noc_router5` | `3853fbc18e1c` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:59: error: A reference to a wire or reg (`o') is not allowed in a constant expression. | Accepted · 5/5 tests · pass formal · 0.9119 · simulation via sv2v |
| [nov14/haiku/none](../2026-11-14/claude-haiku-5-5__none.json) | 34 / 4 / 2 | `noc_router5` | `add91f0a53e3` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:84: error: A reference to a wire or reg (`o') is not allowed in a constant expression. | Accepted · 5/5 tests · pass formal · 0.8400 · simulation via sv2v · canonical synthesis stopped (memory allocation failure) |
| [nov14/haiku/none](../2026-11-14/claude-haiku-5-5__none.json) | 34 / 4 / 3 | `noc_router5` | `2c2d8363c60f` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:84: error: A reference to a wire or reg (`o') is not allowed in a constant expression. | Accepted · 5/5 tests · pass formal · 0.8400 · simulation via sv2v · canonical synthesis stopped (time limit) |
| [nov14/sonnet/none](../2026-11-14/claude-sonnet-5-5__none.json) | 34 / 4 / 2 | `noc_router5` | `06800a12793a` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:17: syntax error | Accepted · 5/5 tests · pass formal · 0.8400 · simulation via sv2v · canonical synthesis stopped (memory allocation failure) |
| [nov14/sonnet/none](../2026-11-14/claude-sonnet-5-5__none.json) | 35 / 5 / 2 | `noc_router5` | `1e1bc85a183d` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:65: error: A reference to a wire or reg (`o') is not allowed in a constant expression. | Tool resource limit · 5/5 tests · timeout formal · 0.8500 · simulation via sv2v · formal time limit |
| [run-a/haiku/full](run-a/claude-haiku-5-5__full.json) | 41 / 1 / 1 | `noc_router5` | `efb2fede85d4` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:48: error: A reference to a wire or reg (`i') is not allowed in a constant expression. | Accepted · 5/5 tests · pass formal · 0.9092 · simulation via sv2v |
| [run-a/haiku/none](run-a/claude-haiku-5-5__none.json) | 41 / 1 / 1 | `noc_router5` | `efb2fede85d4` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:48: error: A reference to a wire or reg (`i') is not allowed in a constant expression. | Accepted · 5/5 tests · pass formal · 0.9092 · simulation via sv2v |
| [run-a/haiku/none](run-a/claude-haiku-5-5__none.json) | 41 / 1 / 2 | `noc_router5` | `55fb5644cd52` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:48: error: A reference to a wire or reg (`i') is not allowed in a constant expression. | Accepted · 5/5 tests · pass formal · 0.9084 · simulation via sv2v |
| [run-a/haiku/none](run-a/claude-haiku-5-5__none.json) | 41 / 1 / 3 | `noc_router5` | `5c05afe94cc0` | 0/0 tests · skipped formal · 0.0000 · p/rtlgym_noc_router5_qw29nobv/candidate.sv:79: error: Array index expressions must be constant here. | Accepted · 5/5 tests · pass formal · 0.9355 · simulation via sv2v |
| [run-a/sonnet/full](run-a/claude-sonnet-5-5__full.json) | 44 / 4 / 2 | `noc_router5` | `3408d7c1a886` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:56: error: A reference to a wire or reg (`o') is not allowed in a constant expression. | Accepted · 5/5 tests · pass formal · 0.9255 · simulation via sv2v |
| [run-a/sonnet/none](run-a/claude-sonnet-5-5__none.json) | 41 / 1 / 3 | `noc_router5` | `45a7ed6c4e1a` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:57: error: A reference to a wire or reg (`d') is not allowed in a constant expression. | Functional mismatch · 4/5 tests · fail formal · 0.7100 · simulation via sv2v |
| [run-b/haiku/full](run-b/claude-haiku-5-5__full.json) | 10 / 1 / 1 | `axi4_burst_slave` | `72dc48a3780b` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:208: error: Unresolved net/uwire s_axi_bid cannot have multiple drivers. | Still rejected at compile · 0/0 tests · skipped formal · 0.0000 |
| [run-b/haiku/none](run-b/claude-haiku-5-5__none.json) | 10 / 1 / 1 | `axi4_burst_slave` | `72dc48a3780b` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:208: error: Unresolved net/uwire s_axi_bid cannot have multiple drivers. | Still rejected at compile · 0/0 tests · skipped formal · 0.0000 |
| [run-b/sonnet/full](run-b/claude-sonnet-5-5__full.json) | 21 / 3 / 3 | `noc_router5` | `3d3ea42eb5dd` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:60: error: A reference to a wire or reg (`o') is not allowed in a constant expression. | Accepted · 5/5 tests · pass formal · 0.9700 · simulation via sv2v |
| [run-b/sonnet/none](run-b/claude-sonnet-5-5__none.json) | 19 / 1 / 3 | `noc_router5` | `d0a44df34d87` | 0/5 tests · pass formal · 0.1400 · The simulation timed out (a loop that never ends or logic that never settles); tests that did not finish count as failed. | Simulation timeout · 0/5 tests · pass formal · 0.1400 · simulation via native |
| [run8/haiku/full](repair-pilot/claude-haiku-5-5__full.json) | 3 / 1 / 1 | `repair_noc_router5` | `fe077614d352` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:65: error: A reference to a wire or reg (`d') is not allowed in a constant expression. | Tool resource limit · 5/5 tests · timeout formal · 0.4900 · simulation via sv2v · formal time limit · synthesis time limit |
| [run8/haiku/none](repair-pilot/claude-haiku-5-5__none.json) | 3 / 1 / 1 | `repair_noc_router5` | `fe077614d352` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:65: error: A reference to a wire or reg (`d') is not allowed in a constant expression. | Tool resource limit · 5/5 tests · timeout formal · 0.4900 · simulation via sv2v · formal time limit · synthesis time limit |
| [run8/haiku/full](repair-pilot/claude-haiku-5-5__full.json) | 3 / 1 / 2 | `repair_noc_router5` | `af4522687851` | 0/0 tests · skipped formal · 0.0000 · candidate.sv:58: error: A reference to a wire or reg (`d') is not allowed in a constant expression. | Tool resource limit · 5/5 tests · timeout formal · 0.4900 · simulation via sv2v · formal time limit · synthesis time limit |

## Repair pilot router resource stop

The unaccepted turn was `repair_noc_router5`, Haiku full-feedback turn 3 in `26_11_16__run8/claude-haiku-5-5__full.json` (grader commit `96a0371`). The submitted source SHA-256 is `89c2557d252c9767d9c900b922a0a2d4b8333446fd5eb0db26a8f0782436b948`. Icarus passed 5/5 simulation tests and Verilator lint was clean. The archive recorded canonical and alternate synthesis timeouts at 60 seconds each, 120.077 seconds combined, and a formal wrapper timeout at 255.222 seconds. The result was inconclusive. In the same run, Haiku's no-feedback turn 2 also used a wide `% 5` expression and passed with alternate synthesis in 16.808 seconds and formal in 39.240 seconds.

An offline trace of the unchanged source used Yosys 0.33 (`2584903a060`) and pinned sv2v 0.0.13 under WSL. The converter succeeded in 0.066 seconds for the synthesis profile. The diagnostic invocation ran the existing alternate synthesis sequence with a Yosys log file (`yosys -q -l alternate.log -p "<sequence>"`). The log stopped at `PROC_DLATCH` during the initial `read_verilog; hierarchy; proc` sequence after 60.007 seconds. It never reached the interface report, coarse synthesis, or the constant-five mapper. Keeping all process passes and adding early constant folding and identical-cell merging still stopped in `PROC_DLATCH` after 60.151 seconds. The existing formal script, run with a shorter diagnostic deadline, stopped in the candidate's `PROC_DLATCH` after 25.007 seconds. It had applied the original depth and parameter profile (8 cycles at `PAYLOAD_W=1, X=1, Y=1`) and never entered SAT.

The candidate uses the wide remainder to produce an arbitration index and writes it back through `gnt[5*d + idx] = 1'b1` in the nested combinational scan. A diagnostic copy kept the remainder and changed that one packed dynamic write to five fixed-index writes gated by `idx == j`. The same alternate flow saw all 25 remainder cells, mapped them, and finished a fully lowered generic netlist with `check -assert` in 3.577 seconds (135.17 MB peak, 2,956 cells, no stored latches after optimization). This supports the packed-write/latch-analysis diagnosis for the saved submission. The diagnostic source was changed for profiling, so the synthesis result does not establish acceptance or equivalence of the archived submission.

The mapper remains appropriate for failures that reach technology mapping. This case stalls before that stage. Preserve the current latch pass, formal bound, deadlines, and reward formula. The archived grading result stays inconclusive.
