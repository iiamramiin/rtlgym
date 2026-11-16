## rtlgym eval

Models: claude-sonnet-5-5,claude-haiku-5-5. Tasks: secded_ecc,gearbox_16to12,async_fifo,axi4_burst_slave,cache_controller,packet_checksum,noc_router5. 3 episode(s) per task, up to 3 attempts, paired=true, effort=model default, workers=4. Planned: at most 210 API calls.

| Arm | Episodes (errors) | Accepted on 1st attempt | 1st attempt passes tests | Accepted within N turns | Test escapes | Inconclusive | Mean turns | Grading p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 (feedback full, paired) | 21 (0) | 16/21 (76%) | 18/21 (86%) | 20/21 (95%) (N=3) | 0 | 5 | 1.333 | 1.476 s / 81.099 s |
| claude-haiku-5-5 (feedback none, paired) | 21 (0) | 16/21 (76%) | 18/21 (86%) | 18/21 (86%) (N=3) | 0 | 5 | 1.381 | 50.065 s / 69.621 s |
| claude-sonnet-5-5 (feedback full, paired) | 21 (0) | 18/21 (86%) | 20/21 (95%) | 20/21 (95%) (N=3) | 0 | 2 | 1.19 | 1.155 s / 123.829 s |
| claude-sonnet-5-5 (feedback none, paired) | 21 (0) | 18/21 (86%) | 20/21 (95%) | 19/21 (90%) (N=3) | 0 | 6 | 1.238 | 120.351 s / 122.04 s |

### Acceptance by verification mode

| Arm | Verification | Episodes (errors) | First attempt | Within turn budget |
|---|---|---:|---:|---:|
| claude-haiku-5-5 (feedback full, paired) | Formal enabled | 18 (0) | 13/18 | 17/18 |
| claude-haiku-5-5 (feedback full, paired) | Simulation only | 3 (0) | 3/3 | 3/3 |
| claude-haiku-5-5 (feedback none, paired) | Formal enabled | 18 (0) | 13/18 | 15/18 |
| claude-haiku-5-5 (feedback none, paired) | Simulation only | 3 (0) | 3/3 | 3/3 |
| claude-sonnet-5-5 (feedback full, paired) | Formal enabled | 18 (0) | 15/18 | 17/18 |
| claude-sonnet-5-5 (feedback full, paired) | Simulation only | 3 (0) | 3/3 | 3/3 |
| claude-sonnet-5-5 (feedback none, paired) | Formal enabled | 18 (0) | 15/18 | 16/18 |
| claude-sonnet-5-5 (feedback none, paired) | Simulation only | 3 (0) | 3/3 | 3/3 |

| Task | claude-haiku-5-5 (feedback full, paired) | claude-haiku-5-5 (feedback none, paired) | claude-sonnet-5-5 (feedback full, paired) | claude-sonnet-5-5 (feedback none, paired) |
|---|---:|---:|---:|---:|
| async_fifo | 3/3 (100%) → 3/3 (100%) (simulation only) | 3/3 (100%) → 3/3 (100%) (simulation only) | 3/3 (100%) → 3/3 (100%) (simulation only) | 3/3 (100%) → 3/3 (100%) (simulation only) |
| axi4_burst_slave | 2/3 (67%) → 3/3 (100%) | 2/3 (67%) → 3/3 (100%) | 3/3 (100%) → 3/3 (100%) | 3/3 (100%) → 3/3 (100%) |
| cache_controller | 3/3 (100%) → 3/3 (100%) | 3/3 (100%) → 3/3 (100%) | 3/3 (100%) → 3/3 (100%) | 3/3 (100%) → 3/3 (100%) |
| gearbox_16to12 | 3/3 (100%) → 3/3 (100%) | 3/3 (100%) → 3/3 (100%) | 3/3 (100%) → 3/3 (100%) | 3/3 (100%) → 3/3 (100%) |
| noc_router5 | 0/3 (0%) → 2/3 (67%) | 0/3 (0%) → 0/3 (0%) | 0/3 (0%) → 2/3 (67%) | 0/3 (0%) → 1/3 (33%) |
| packet_checksum | 2/3 (67%) → 3/3 (100%) | 2/3 (67%) → 3/3 (100%) | 3/3 (100%) → 3/3 (100%) | 3/3 (100%) → 3/3 (100%) |
| secded_ecc | 3/3 (100%) → 3/3 (100%) | 3/3 (100%) → 3/3 (100%) | 3/3 (100%) → 3/3 (100%) | 3/3 (100%) → 3/3 (100%) |

Per-task cells: accepted on the first attempt → accepted within the turn budget. Accepted means every hidden test passed, the design synthesized without latches, and the formal check passed where enabled. Commit e12a9a3; Yosys 0.33 (git sha1 2584903a060).

**WARNING:** **Inconclusive attempts: 18** (the grader could not decide, e.g. a tool hit its time limit; these count as not accepted). Check the per-arm rows below.

**Errored episodes: 0** (e.g. API errors; counted as unsolved).

- claude-haiku-5-5, feedback full: 5 inconclusive, 0 errored
- claude-haiku-5-5, feedback none: 5 inconclusive, 0 errored
- claude-sonnet-5-5, feedback full: 2 inconclusive, 0 errored
- claude-sonnet-5-5, feedback none: 6 inconclusive, 0 errored

### Front-end and resource failures by arm

| Model | Feedback | Front-end failures | Resource failures |
|---|---|---:|---:|
| claude-haiku-5-5 | full | 0 | 5 |
| claude-haiku-5-5 | none | 0 | 5 |
| claude-sonnet-5-5 | full | 0 | 2 |
| claude-sonnet-5-5 | none | 0 | 5 |

### Tokens per model

| Model | API calls | Input tokens | Output tokens (thinking included) |
|---|---:|---:|---:|
| claude-haiku-5-5 | 36 | 157,078 | 151,288 |
| claude-sonnet-5-5 | 30 | 78,989 | 74,026 |

Cost = input tokens x input price + output tokens x output price; check the current prices at https://platform.claude.com/docs/en/about-claude/pricing.

### Paired outcomes (same first attempt in both arms)

| Model | Episodes | Solved in both | Only full | Only none | In neither | Errored | Informative | Discordant | Exact McNemar p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 | 21 | 18 | 2 | 0 | 1 | 0 | 5 | 2 | 0.5 |
| claude-sonnet-5-5 | 21 | 18 | 2 | 1 | 0 | 0 | 3 | 3 | 1.0 |

### Paired outcomes by verification mode

| Model | Verification | Episodes | Solved in both | Only full | Only none | In neither | Errored | Informative | Discordant | Exact McNemar p |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 | Formal enabled | 18 | 15 | 2 | 0 | 1 | 0 | 5 | 2 | 0.5 |
| claude-haiku-5-5 | Simulation only | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 1.0 |
| claude-sonnet-5-5 | Formal enabled | 18 | 15 | 2 | 1 | 0 | 0 | 3 | 3 | 1.0 |
| claude-sonnet-5-5 | Simulation only | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 1.0 |

Informative: first attempt not accepted (only these can differ between the arms). Discordant: solved in exactly one arm.
