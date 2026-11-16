# November 16 router regrade

Run A and Run B recorded 75 `noc_router5` turns and 59 distinct submitted sources. The table maps each archived turn to its source's offline grade. Shared first attempts can occupy two archival rows. SHA-256 uses the exact submitted text.

The archive keeps its original feedback, outcomes and tool reports. The offline grade uses the recorded RTL and makes no new model calls.

## Diagnosis

Two sampled synthesis allocation failures stopped in Yosys TECHMAP while expanding `$mod` cells at a 2 GiB address-space limit. A representative also failed at 4 GiB. A coarse synthesis check counted 25 `$mod` cells before technology mapping. The measurement locates the expensive expansion in the sampled sources. Narrowly bounded circular-index arithmetic can reduce the gate mapping cost.

## Offline grading policy

The offline check keeps the original router task and sources. Formal compares
outputs for eight cycles after reset with `PAYLOAD_W=1`, `X=1`, and `Y=1`.
Its solver deadline remains 240 seconds. The wrapper allows 255 seconds wall
time and 260 CPU seconds for the formal process. Shorter tool stages keep the
120 CPU-second floor. The address-space limit remains 2 GiB per tool process.

Canonical synthesis still runs first. When it runs out of memory or time after parsing,
the alternate synthesis path maps constant-divisor-five remainder cells and
checks a fully lowered netlist. The retry must finish, pass Yosys structural
checks, and leave no unmapped cells. The same simulation, interface, latch and
formal requirements still apply. An alternate mapping can establish synthesis
success. Only the canonical flow supplies comparable cell-count and depth
proxies, so the alternate path reports them as unavailable and earns no PPA
bonus. An unresolved resource stop stays inconclusive when simulation passes.

The replay used Yosys 0.33 and sv2v 0.0.13 under Ubuntu 24.04 in WSL. Where the
canonical replay hit a wall timeout before emitting an allocation error, the
updated synthesis retry was run separately and joined to the replayed
simulation and formal outcomes for the same source hash. Those synthesis
durations are sums of stages rather than a single elapsed episode time.

## Offline outcome summary

Completed 59/59 distinct sources. Accepted after historical resource stops: 8/25. Historically accepted sources accepted offline: 15/16.

All 15 distinct designs that previously failed synthesis allocation passed
the alternate netlist checks. Seven also passed formal and were accepted.
Six still had formal errors and two hit the formal time limit. Five of the
eight Run B Haiku designs with synthesis allocation failures were accepted.
Of ten designs previously killed during formal checking, one proved and the
other nine hit the formal wall deadline.

One previously accepted source (`b1c3f4e91cd8`) passed synthesis and all five
simulation tests but hit the formal wall deadline on two local replays. Its
archived proof passed in 118.957 seconds. Both local outcomes stayed inconclusive.

| Offline class | Distinct sources |
| --- | ---: |
| Accepted | 16 |
| Accepted, canonical proxy unavailable | 7 |
| Formal error | 6 |
| Functional mismatch | 7 |
| Icarus elaboration failure | 6 |
| Latch error | 4 |
| Simulation timeout | 1 |
| Tool resource stop | 12 |

| Historical resource stage | Distinct sources | Regraded | Accepted offline |
| --- | ---: | ---: | ---: |
| formal | 10 | 10 | 1 |
| synthesis | 15 | 15 | 7 |

| Historical class | Offline class | Archived turn rows |
| --- | --- | ---: |
| Accepted | Accepted | 18 |
| Accepted | Tool resource stop | 1 |
| Functional mismatch | Functional mismatch | 9 |
| Icarus elaboration failure | Icarus elaboration failure | 7 |
| Latch error | Functional mismatch | 1 |
| Latch error | Latch error | 6 |
| Simulation timeout | Simulation timeout | 1 |
| Tool resource stop | Accepted | 2 |
| Tool resource stop | Accepted, canonical proxy unavailable | 10 |
| Tool resource stop | Formal error | 7 |
| Tool resource stop | Tool resource stop | 13 |

## Turn-by-turn detail

Episode numbers are one-based within the router task in the linked arm.

| Archived location | Source SHA-256 prefix | Historical class | Historical grade | Offline class | Offline grade |
| --- | --- | --- | --- | --- | --- |
| [run-a haiku full E1 T1](run-a/claude-haiku-5-5__full.json) | `efb2fede85d4` | Icarus elaboration failure | 0/0 sim · skipped formal · score 0.0000 | Icarus elaboration failure | 0/0 sim · skipped formal · score 0.0000 |
| [run-a haiku full E1 T2](run-a/claude-haiku-5-5__full.json) | `b1c3f4e91cd8` | Accepted | 5/5 sim · pass formal · score 0.8588 · synth 14.821 s, formal 118.957 s | Tool resource stop | 5/5 sim · timeout formal · formal: time limit · score 0.8000 · synth 13.115 s, formal 255.483 s |
| [run-a haiku full E2 T1](run-a/claude-haiku-5-5__full.json) | `a38598d45601` | Tool resource stop | 5/5 sim · pass formal · synthesis: memory allocation failure · score 0.4900 · synth 33.752 s, formal 68.826 s | Accepted, canonical proxy unavailable | 5/5 sim · pass formal · canonical synthesis stopped (time limit) · score 0.8400 · synth 67.628 s, formal 136.106 s |
| [run-a haiku full E2 T2](run-a/claude-haiku-5-5__full.json) | `4143541e4ca3` | Accepted | 5/5 sim · pass formal · score 0.9250 · synth 4.822 s, formal 44.811 s | Accepted | 5/5 sim · pass formal · score 0.9250 · synth 10.056 s, formal 88.015 s |
| [run-a haiku full E3 T1](run-a/claude-haiku-5-5__full.json) | `720c373829a2` | Accepted | 5/5 sim · pass formal · score 0.8907 · synth 8.492 s, formal 83.846 s | Accepted | 5/5 sim · pass formal · score 0.8907 · synth 8.624 s, formal 177.032 s |
| [run-a haiku full E4 T1](run-a/claude-haiku-5-5__full.json) | `75d7fae3b4eb` | Accepted | 5/5 sim · pass formal · score 0.9169 · synth 10.273 s, formal 103.811 s | Accepted | 5/5 sim · pass formal · score 0.9169 · synth 8.079 s, formal 179.677 s |
| [run-a haiku full E5 T1](run-a/claude-haiku-5-5__full.json) | `1ff4bda1db9f` | Accepted | 5/5 sim · pass formal · score 0.9091 · synth 4.464 s, formal 50.578 s | Accepted | 5/5 sim · pass formal · score 0.9091 · synth 4.858 s, formal 93.377 s |
| [run-a haiku none E1 T1](run-a/claude-haiku-5-5__none.json) | `efb2fede85d4` | Icarus elaboration failure | 0/0 sim · skipped formal · score 0.0000 | Icarus elaboration failure | 0/0 sim · skipped formal · score 0.0000 |
| [run-a haiku none E1 T2](run-a/claude-haiku-5-5__none.json) | `55fb5644cd52` | Icarus elaboration failure | 0/0 sim · skipped formal · score 0.0000 | Icarus elaboration failure | 0/0 sim · skipped formal · score 0.0000 |
| [run-a haiku none E1 T3](run-a/claude-haiku-5-5__none.json) | `5c05afe94cc0` | Icarus elaboration failure | 0/0 sim · skipped formal · score 0.0000 | Icarus elaboration failure | 0/0 sim · skipped formal · score 0.0000 |
| [run-a haiku none E2 T1](run-a/claude-haiku-5-5__none.json) | `a38598d45601` | Tool resource stop | 5/5 sim · pass formal · synthesis: memory allocation failure · score 0.4900 · synth 28.899 s, formal 51.447 s | Accepted, canonical proxy unavailable | 5/5 sim · pass formal · canonical synthesis stopped (time limit) · score 0.8400 · synth 67.628 s, formal 136.106 s |
| [run-a haiku none E2 T2](run-a/claude-haiku-5-5__none.json) | `d3cf0ba4ec59` | Tool resource stop | 5/5 sim · pass formal · synthesis: memory allocation failure · score 0.4600 · synth 27.817 s, formal 58.412 s | Accepted, canonical proxy unavailable | 5/5 sim · pass formal · canonical synthesis ran out of memory; alternate netlist checked · score 0.8100 · synth 63.917 s, formal 197.981 s |
| [run-a haiku none E2 T3](run-a/claude-haiku-5-5__none.json) | `fd0b18942bb8` | Latch error | 5/5 sim · error formal · score 0.4500 · synth 0.118 s, formal 0.218 s | Latch error | 5/5 sim · error formal · Yosys latch error · score 0.4500 · synth 0.121 s, formal 0.377 s |
| [run-a haiku none E3 T1](run-a/claude-haiku-5-5__none.json) | `720c373829a2` | Accepted | 5/5 sim · pass formal · score 0.8907 · synth 8.492 s, formal 83.846 s | Accepted | 5/5 sim · pass formal · score 0.8907 · synth 8.624 s, formal 177.032 s |
| [run-a haiku none E4 T1](run-a/claude-haiku-5-5__none.json) | `75d7fae3b4eb` | Accepted | 5/5 sim · pass formal · score 0.9169 · synth 10.273 s, formal 103.811 s | Accepted | 5/5 sim · pass formal · score 0.9169 · synth 8.079 s, formal 179.677 s |
| [run-a haiku none E5 T1](run-a/claude-haiku-5-5__none.json) | `1ff4bda1db9f` | Accepted | 5/5 sim · pass formal · score 0.9091 · synth 4.464 s, formal 50.578 s | Accepted | 5/5 sim · pass formal · score 0.9091 · synth 4.858 s, formal 93.377 s |
| [run-a sonnet full E1 T1](run-a/claude-sonnet-5-5__full.json) | `85dc821b2d33` | Latch error | 4/5 sim · error formal · score 0.4200 · synth 0.167 s, formal 0.319 s | Latch error | 4/5 sim · error formal · Yosys latch error · score 0.4200 · synth 0.221 s, formal 0.570 s |
| [run-a sonnet full E1 T2](run-a/claude-sonnet-5-5__full.json) | `589b1054caa3` | Tool resource stop | 5/5 sim · error formal · formal: killed by SIGKILL · score 0.8500 · synth 18.661 s, formal 130.025 s | Tool resource stop | 5/5 sim · timeout formal · formal: time limit · score 0.8500 · synth 13.708 s, formal 255.332 s |
| [run-a sonnet full E1 T3](run-a/claude-sonnet-5-5__full.json) | `53dd2cc88561` | Accepted | 5/5 sim · pass formal · score 0.9780 · synth 4.435 s, formal 21.687 s | Accepted | 5/5 sim · pass formal · score 0.9780 · synth 4.667 s, formal 39.676 s |
| [run-a sonnet full E2 T1](run-a/claude-sonnet-5-5__full.json) | `949f1a03a520` | Tool resource stop | 5/5 sim · error formal · formal: killed by SIGKILL · score 0.8500 · synth 7.729 s, formal 129.104 s | Accepted | 5/5 sim · pass formal · score 0.9123 · synth 7.431 s, formal 199.342 s |
| [run-a sonnet full E2 T2](run-a/claude-sonnet-5-5__full.json) | `aa3a5ddbdb1d` | Accepted | 5/5 sim · pass formal · score 0.9703 · synth 1.783 s, formal 10.960 s | Accepted | 5/5 sim · pass formal · score 0.9703 · synth 1.653 s, formal 15.613 s |
| [run-a sonnet full E3 T1](run-a/claude-sonnet-5-5__full.json) | `6069c22ecdad` | Functional mismatch | 4/5 sim · fail formal · score 0.7100 · synth 4.459 s, formal 3.060 s | Functional mismatch | 4/5 sim · fail formal · score 0.7100 · synth 6.559 s, formal 4.913 s |
| [run-a sonnet full E3 T2](run-a/claude-sonnet-5-5__full.json) | `f38580c04729` | Accepted | 5/5 sim · pass formal · score 0.9139 · synth 4.166 s, formal 91.347 s | Accepted | 5/5 sim · pass formal · score 0.9139 · synth 6.018 s, formal 147.487 s |
| [run-a sonnet full E4 T1](run-a/claude-sonnet-5-5__full.json) | `11042725e477` | Latch error | 5/5 sim · error formal · score 0.4800 · synth 0.174 s, formal 0.423 s | Latch error | 5/5 sim · error formal · Yosys latch error · score 0.4800 · synth 0.171 s, formal 0.425 s |
| [run-a sonnet full E4 T2](run-a/claude-sonnet-5-5__full.json) | `3408d7c1a886` | Icarus elaboration failure | 0/0 sim · skipped formal · score 0.0000 | Icarus elaboration failure | 0/0 sim · skipped formal · score 0.0000 |
| [run-a sonnet full E4 T3](run-a/claude-sonnet-5-5__full.json) | `d1fb4936ba1a` | Accepted | 5/5 sim · pass formal · score 0.9307 · synth 5.869 s, formal 29.585 s | Accepted | 5/5 sim · pass formal · score 0.9307 · synth 5.529 s, formal 46.650 s |
| [run-a sonnet full E5 T1](run-a/claude-sonnet-5-5__full.json) | `321171a4136e` | Tool resource stop | 5/5 sim · error formal · synthesis: memory allocation failure · score 0.4900 · synth 37.820 s, formal 28.795 s | Formal error | 5/5 sim · error formal · canonical synthesis stopped (time limit) · score 0.8400 · synth 80.602 s, formal 41.284 s |
| [run-a sonnet full E5 T2](run-a/claude-sonnet-5-5__full.json) | `e1a7c76930cf` | Accepted | 5/5 sim · pass formal · score 0.9631 · synth 2.618 s, formal 16.317 s | Accepted | 5/5 sim · pass formal · score 0.9631 · synth 2.659 s, formal 31.101 s |
| [run-a sonnet none E1 T1](run-a/claude-sonnet-5-5__none.json) | `85dc821b2d33` | Latch error | 4/5 sim · error formal · score 0.4200 · synth 0.167 s, formal 0.319 s | Latch error | 4/5 sim · error formal · Yosys latch error · score 0.4200 · synth 0.221 s, formal 0.570 s |
| [run-a sonnet none E1 T2](run-a/claude-sonnet-5-5__none.json) | `93f262cac4ba` | Latch error | 4/5 sim · fail formal · score 0.7000 · synth 8.163 s, formal 4.474 s | Functional mismatch | 4/5 sim · fail formal · score 0.7000 · synth 6.196 s, formal 4.955 s |
| [run-a sonnet none E1 T3](run-a/claude-sonnet-5-5__none.json) | `45a7ed6c4e1a` | Icarus elaboration failure | 0/0 sim · skipped formal · score 0.0000 | Icarus elaboration failure | 0/0 sim · skipped formal · score 0.0000 |
| [run-a sonnet none E2 T1](run-a/claude-sonnet-5-5__none.json) | `949f1a03a520` | Tool resource stop | 5/5 sim · error formal · formal: killed by SIGKILL · score 0.8500 · synth 9.910 s, formal 130.385 s | Accepted | 5/5 sim · pass formal · score 0.9123 · synth 7.431 s, formal 199.342 s |
| [run-a sonnet none E2 T2](run-a/claude-sonnet-5-5__none.json) | `8a7f4361855b` | Tool resource stop | 5/5 sim · error formal · formal: killed by SIGKILL · score 0.8500 · synth 18.665 s, formal 131.077 s | Tool resource stop | 5/5 sim · timeout formal · formal: time limit · score 0.8500 · synth 10.284 s, formal 255.287 s |
| [run-a sonnet none E2 T3](run-a/claude-sonnet-5-5__none.json) | `c26578cda3f5` | Accepted | 5/5 sim · pass formal · score 0.9325 · synth 2.555 s, formal 52.500 s | Accepted | 5/5 sim · pass formal · score 0.9325 · synth 4.662 s, formal 180.416 s |
| [run-a sonnet none E3 T1](run-a/claude-sonnet-5-5__none.json) | `6069c22ecdad` | Functional mismatch | 4/5 sim · fail formal · score 0.7100 · synth 4.459 s, formal 3.060 s | Functional mismatch | 4/5 sim · fail formal · score 0.7100 · synth 6.559 s, formal 4.913 s |
| [run-a sonnet none E3 T2](run-a/claude-sonnet-5-5__none.json) | `5f0b1a3937d8` | Tool resource stop | 5/5 sim · error formal · formal: killed by SIGKILL · score 0.8500 · synth 13.249 s, formal 130.907 s | Tool resource stop | 5/5 sim · timeout formal · formal: time limit · score 0.8500 · synth 13.505 s, formal 255.239 s |
| [run-a sonnet none E3 T3](run-a/claude-sonnet-5-5__none.json) | `334c16476dbe` | Tool resource stop | 5/5 sim · error formal · formal: killed by SIGKILL · score 0.8500 · synth 21.079 s, formal 134.480 s | Tool resource stop | 5/5 sim · timeout formal · formal: time limit · score 0.8500 · synth 14.753 s, formal 255.307 s |
| [run-a sonnet none E4 T1](run-a/claude-sonnet-5-5__none.json) | `11042725e477` | Latch error | 5/5 sim · error formal · score 0.4800 · synth 0.174 s, formal 0.423 s | Latch error | 5/5 sim · error formal · Yosys latch error · score 0.4800 · synth 0.171 s, formal 0.425 s |
| [run-a sonnet none E4 T2](run-a/claude-sonnet-5-5__none.json) | `bebaf2d79511` | Tool resource stop | 5/5 sim · error formal · synthesis: memory allocation failure · score 0.4900 · synth 38.153 s, formal 33.546 s | Formal error | 5/5 sim · error formal · canonical synthesis ran out of memory; alternate netlist checked · score 0.8400 · synth 49.409 s, formal 28.320 s |
| [run-a sonnet none E4 T3](run-a/claude-sonnet-5-5__none.json) | `04aca52d960e` | Tool resource stop | 5/5 sim · error formal · synthesis: memory allocation failure · score 0.4500 · synth 34.250 s, formal 25.425 s | Formal error | 5/5 sim · error formal · canonical synthesis stopped (time limit) · score 0.8000 · synth 75.866 s, formal 40.408 s |
| [run-a sonnet none E5 T1](run-a/claude-sonnet-5-5__none.json) | `321171a4136e` | Tool resource stop | 5/5 sim · error formal · synthesis: memory allocation failure · score 0.4900 · synth 35.351 s, formal 29.331 s | Formal error | 5/5 sim · error formal · canonical synthesis stopped (time limit) · score 0.8400 · synth 80.602 s, formal 41.284 s |
| [run-a sonnet none E5 T2](run-a/claude-sonnet-5-5__none.json) | `8edde117a3e9` | Tool resource stop | 5/5 sim · error formal · synthesis: memory allocation failure · score 0.5000 · synth 42.116 s, formal 36.147 s | Formal error | 5/5 sim · error formal · canonical synthesis stopped (time limit) · score 0.8500 · synth 78.719 s, formal 71.915 s |
| [run-a sonnet none E5 T3](run-a/claude-sonnet-5-5__none.json) | `5aad8e2e4109` | Tool resource stop | 5/5 sim · error formal · synthesis: memory allocation failure · score 0.5000 · synth 35.703 s, formal 31.759 s | Formal error | 5/5 sim · error formal · canonical synthesis ran out of memory; alternate netlist checked · score 0.8500 · synth 73.865 s, formal 42.943 s |
| [run-b haiku full E1 T1](run-b/claude-haiku-5-5__full.json) | `70cd411f539d` | Tool resource stop | 5/5 sim · pass formal · synthesis: memory allocation failure · score 0.4500 · synth 34.754 s, formal 68.635 s | Accepted, canonical proxy unavailable | 5/5 sim · pass formal · canonical synthesis stopped (time limit) · score 0.8000 · synth 69.968 s, formal 217.211 s |
| [run-b haiku full E1 T2](run-b/claude-haiku-5-5__full.json) | `1df73835fcd8` | Tool resource stop | 5/5 sim · pass formal · synthesis: memory allocation failure · score 0.4900 · synth 20.749 s, formal 62.514 s | Accepted, canonical proxy unavailable | 5/5 sim · pass formal · canonical synthesis ran out of memory; alternate netlist checked · score 0.8400 · synth 58.580 s, formal 203.466 s |
| [run-b haiku full E1 T3](run-b/claude-haiku-5-5__full.json) | `9f773d083950` | Tool resource stop | 5/5 sim · error formal · synthesis: memory allocation failure · score 0.4500 · synth 23.522 s, formal 20.564 s | Formal error | 5/5 sim · error formal · canonical synthesis ran out of memory; alternate netlist checked · score 0.8000 · synth 52.192 s, formal 31.459 s |
| [run-b haiku full E2 T1](run-b/claude-haiku-5-5__full.json) | `c1826d0309f6` | Tool resource stop | 5/5 sim · pass formal · synthesis: memory allocation failure · score 0.4500 · synth 35.861 s, formal 79.320 s | Accepted, canonical proxy unavailable | 5/5 sim · pass formal · canonical synthesis ran out of memory; alternate netlist checked · score 0.8000 · synth 46.122 s, formal 229.344 s |
| [run-b haiku full E2 T2](run-b/claude-haiku-5-5__full.json) | `3cf37d6d0baf` | Tool resource stop | 5/5 sim · pass formal · synthesis: memory allocation failure · score 0.4500 · synth 24.946 s, formal 82.528 s | Tool resource stop | 5/5 sim · timeout formal · formal: time limit · canonical synthesis ran out of memory; alternate netlist checked · score 0.8000 · synth 48.778 s, formal 255.757 s |
| [run-b haiku full E2 T3](run-b/claude-haiku-5-5__full.json) | `a700adae3435` | Accepted | 5/5 sim · pass formal · score 0.9439 · synth 1.952 s, formal 33.849 s | Accepted | 5/5 sim · pass formal · score 0.9439 · synth 2.151 s, formal 84.317 s |
| [run-b haiku full E3 T1](run-b/claude-haiku-5-5__full.json) | `e9b6bb2e85ab` | Functional mismatch | 4/5 sim · pass formal · score 0.7100 · synth 4.211 s, formal 76.512 s | Functional mismatch | 4/5 sim · pass formal · score 0.7100 · synth 6.940 s, formal 207.744 s |
| [run-b haiku full E3 T2](run-b/claude-haiku-5-5__full.json) | `e78d27de9504` | Accepted | 5/5 sim · pass formal · score 0.9107 · synth 2.599 s, formal 62.772 s | Accepted | 5/5 sim · pass formal · score 0.9107 · synth 10.500 s, formal 180.765 s |
| [run-b haiku none E1 T1](run-b/claude-haiku-5-5__none.json) | `70cd411f539d` | Tool resource stop | 5/5 sim · pass formal · synthesis: memory allocation failure · score 0.4500 · synth 18.254 s, formal 47.432 s | Accepted, canonical proxy unavailable | 5/5 sim · pass formal · canonical synthesis stopped (time limit) · score 0.8000 · synth 69.968 s, formal 217.211 s |
| [run-b haiku none E1 T2](run-b/claude-haiku-5-5__none.json) | `69075a25e1c9` | Tool resource stop | 5/5 sim · pass formal · synthesis: memory allocation failure · score 0.4900 · synth 21.907 s, formal 52.933 s | Accepted, canonical proxy unavailable | 5/5 sim · pass formal · canonical synthesis ran out of memory; alternate netlist checked · score 0.8400 · synth 60.486 s, formal 217.356 s |
| [run-b haiku none E1 T3](run-b/claude-haiku-5-5__none.json) | `053ae1408d0c` | Functional mismatch | 4/5 sim · fail formal · score 0.7000 · synth 2.810 s, formal 2.459 s | Functional mismatch | 4/5 sim · fail formal · score 0.7000 · synth 4.197 s, formal 3.725 s |
| [run-b haiku none E2 T1](run-b/claude-haiku-5-5__none.json) | `c1826d0309f6` | Tool resource stop | 5/5 sim · pass formal · synthesis: memory allocation failure · score 0.4500 · synth 17.155 s, formal 67.102 s | Accepted, canonical proxy unavailable | 5/5 sim · pass formal · canonical synthesis ran out of memory; alternate netlist checked · score 0.8000 · synth 46.122 s, formal 229.344 s |
| [run-b haiku none E2 T2](run-b/claude-haiku-5-5__none.json) | `76b61505715c` | Tool resource stop | 5/5 sim · pass formal · synthesis: memory allocation failure · score 0.4900 · synth 15.690 s, formal 61.531 s | Tool resource stop | 5/5 sim · timeout formal · formal: time limit · canonical synthesis ran out of memory; alternate netlist checked · score 0.8400 · synth 51.531 s, formal 255.822 s |
| [run-b haiku none E2 T3](run-b/claude-haiku-5-5__none.json) | `cf5c68837d9a` | Tool resource stop | 5/5 sim · pass formal · synthesis: memory allocation failure · score 0.4500 · synth 14.963 s, formal 52.674 s | Accepted, canonical proxy unavailable | 5/5 sim · pass formal · canonical synthesis stopped (time limit) · score 0.8000 · synth 70.049 s, formal 181.011 s |
| [run-b haiku none E3 T1](run-b/claude-haiku-5-5__none.json) | `e9b6bb2e85ab` | Functional mismatch | 4/5 sim · pass formal · score 0.7100 · synth 4.211 s, formal 76.512 s | Functional mismatch | 4/5 sim · pass formal · score 0.7100 · synth 6.940 s, formal 207.744 s |
| [run-b haiku none E3 T2](run-b/claude-haiku-5-5__none.json) | `bb870b528bc9` | Functional mismatch | 4/5 sim · pass formal · score 0.7100 · synth 2.477 s, formal 32.624 s | Functional mismatch | 4/5 sim · pass formal · score 0.7100 · synth 4.589 s, formal 111.427 s |
| [run-b haiku none E3 T3](run-b/claude-haiku-5-5__none.json) | `39daeebb2588` | Functional mismatch | 4/5 sim · pass formal · score 0.7100 · synth 3.052 s, formal 54.210 s | Functional mismatch | 4/5 sim · pass formal · score 0.7100 · synth 4.853 s, formal 152.126 s |
| [run-b sonnet full E1 T1](run-b/claude-sonnet-5-5__full.json) | `61e9ba6fd749` | Tool resource stop | 5/5 sim · error formal · formal: killed by SIGKILL · score 0.8500 · synth 8.372 s, formal 123.756 s | Tool resource stop | 5/5 sim · timeout formal · formal: time limit · score 0.8500 · synth 7.366 s, formal 255.274 s |
| [run-b sonnet full E1 T2](run-b/claude-sonnet-5-5__full.json) | `e23cc98a9ecb` | Accepted | 5/5 sim · pass formal · score 0.9768 · synth 1.753 s, formal 8.286 s | Accepted | 5/5 sim · pass formal · score 0.9768 · synth 1.683 s, formal 18.997 s |
| [run-b sonnet full E2 T1](run-b/claude-sonnet-5-5__full.json) | `bc3a099ae491` | Tool resource stop | 5/5 sim · error formal · formal: killed by SIGKILL · score 0.8400 · synth 12.401 s, formal 122.477 s | Tool resource stop | 5/5 sim · timeout formal · formal: time limit · score 0.8400 · synth 22.623 s, formal 255.549 s |
| [run-b sonnet full E2 T2](run-b/claude-sonnet-5-5__full.json) | `1642271675c7` | Accepted | 5/5 sim · pass formal · score 0.9788 · synth 5.992 s, formal 16.520 s | Accepted | 5/5 sim · pass formal · score 0.9788 · synth 14.730 s, formal 62.463 s |
| [run-b sonnet full E3 T1](run-b/claude-sonnet-5-5__full.json) | `170bb031a4e9` | Functional mismatch | 4/5 sim · fail formal · score 0.7000 · synth 7.742 s, formal 6.287 s | Functional mismatch | 4/5 sim · fail formal · score 0.7000 · synth 10.074 s, formal 10.048 s |
| [run-b sonnet full E3 T2](run-b/claude-sonnet-5-5__full.json) | `26a30d75f0ce` | Latch error | 5/5 sim · error formal · score 0.4500 · synth 0.621 s, formal 1.179 s | Latch error | 5/5 sim · error formal · Yosys latch error · score 0.4500 · synth 1.192 s, formal 2.372 s |
| [run-b sonnet full E3 T3](run-b/claude-sonnet-5-5__full.json) | `3d3ea42eb5dd` | Icarus elaboration failure | 0/0 sim · skipped formal · score 0.0000 | Icarus elaboration failure | 0/0 sim · skipped formal · score 0.0000 |
| [run-b sonnet none E1 T1](run-b/claude-sonnet-5-5__none.json) | `61e9ba6fd749` | Tool resource stop | 5/5 sim · error formal · formal: killed by SIGKILL · score 0.8500 · synth 4.956 s, formal 120.283 s | Tool resource stop | 5/5 sim · timeout formal · formal: time limit · score 0.8500 · synth 7.366 s, formal 255.274 s |
| [run-b sonnet none E1 T2](run-b/claude-sonnet-5-5__none.json) | `e4ccf1fdcb5f` | Tool resource stop | 5/5 sim · error formal · formal: killed by SIGKILL · score 0.8500 · synth 4.254 s, formal 120.333 s | Tool resource stop | 5/5 sim · timeout formal · formal: time limit · score 0.8500 · synth 18.345 s, formal 255.603 s |
| [run-b sonnet none E1 T3](run-b/claude-sonnet-5-5__none.json) | `d0a44df34d87` | Simulation timeout | 0/5 sim · pass formal · score 0.1400 · synth 3.263 s, formal 47.084 s | Simulation timeout | 0/5 sim · pass formal · score 0.1400 · synth 6.356 s, formal 122.385 s |
| [run-b sonnet none E2 T1](run-b/claude-sonnet-5-5__none.json) | `bc3a099ae491` | Tool resource stop | 5/5 sim · error formal · formal: killed by SIGKILL · score 0.8400 · synth 8.512 s, formal 120.362 s | Tool resource stop | 5/5 sim · timeout formal · formal: time limit · score 0.8400 · synth 22.623 s, formal 255.549 s |
| [run-b sonnet none E2 T2](run-b/claude-sonnet-5-5__none.json) | `360293838657` | Tool resource stop | 5/5 sim · error formal · formal: killed by SIGKILL · score 0.8500 · synth 17.312 s, formal 120.345 s | Tool resource stop | 5/5 sim · timeout formal · formal: time limit · score 0.8500 · synth 51.162 s, formal 255.606 s |
| [run-b sonnet none E2 T3](run-b/claude-sonnet-5-5__none.json) | `f71ebb7b8df2` | Tool resource stop | 5/5 sim · error formal · formal: killed by SIGKILL · score 0.8500 · synth 12.731 s, formal 121.402 s | Tool resource stop | 5/5 sim · timeout formal · formal: time limit · score 0.8500 · synth 43.578 s, formal 256.090 s |
| [run-b sonnet none E3 T1](run-b/claude-sonnet-5-5__none.json) | `170bb031a4e9` | Functional mismatch | 4/5 sim · fail formal · score 0.7000 · synth 7.742 s, formal 6.287 s | Functional mismatch | 4/5 sim · fail formal · score 0.7000 · synth 10.074 s, formal 10.048 s |
| [run-b sonnet none E3 T2](run-b/claude-sonnet-5-5__none.json) | `bf481be792e5` | Accepted | 5/5 sim · pass formal · score 0.9044 · synth 5.190 s, formal 76.708 s | Accepted | 5/5 sim · pass formal · score 0.9044 · synth 13.829 s, formal 145.051 s |
