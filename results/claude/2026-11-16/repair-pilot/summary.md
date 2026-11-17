## rtlgym eval

Models: claude-sonnet-5-5,claude-haiku-5-5. Tasks: repair_popcount16,repair_rr_arbiter4,repair_noc_router5,repair_axi4_burst_slave,repair_cache_controller,repair_axil_regs,repair_gearbox_16to12,repair_secded_ecc. 1 episode(s) per task, up to 3 attempts, paired=true, effort=model default, workers=4. Planned: at most 80 API calls.

| Arm | Episodes (errors) | Accepted on 1st attempt | 1st attempt passes tests | Accepted within N turns | Test escapes | Inconclusive | Mean turns | Grading p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 (feedback full, paired) | 8 (0) | 7/8 (88%) | 7/8 (88%) | 7/8 (88%) (N=3) | 0 | 1 | 1.25 | 0.694 s / 379.423 s |
| claude-haiku-5-5 (feedback none, paired) | 8 (0) | 7/8 (88%) | 7/8 (88%) | 8/8 (100%) (N=3) | 0 | 0 | 1.125 | 0.798 s / 57.072 s |
| claude-sonnet-5-5 (feedback full, paired) | 8 (0) | 8/8 (100%) | 8/8 (100%) | 8/8 (100%) (N=3) | 0 | 0 | 1.0 | 0.936 s / 74.143 s |
| claude-sonnet-5-5 (feedback none, paired) | 8 (0) | 8/8 (100%) | 8/8 (100%) | 8/8 (100%) (N=3) | 0 | 0 | 1.0 | 0.936 s / 74.143 s |

### Acceptance by verification mode

| Arm | Verification | Episodes (errors) | First attempt | Within turn budget |
|---|---|---:|---:|---:|
| claude-haiku-5-5 (feedback full, paired) | Formal enabled | 8 (0) | 7/8 | 7/8 |
| claude-haiku-5-5 (feedback none, paired) | Formal enabled | 8 (0) | 7/8 | 8/8 |
| claude-sonnet-5-5 (feedback full, paired) | Formal enabled | 8 (0) | 8/8 | 8/8 |
| claude-sonnet-5-5 (feedback none, paired) | Formal enabled | 8 (0) | 8/8 | 8/8 |

| Task | claude-haiku-5-5 (feedback full, paired) | claude-haiku-5-5 (feedback none, paired) | claude-sonnet-5-5 (feedback full, paired) | claude-sonnet-5-5 (feedback none, paired) |
|---|---:|---:|---:|---:|
| repair_axi4_burst_slave | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) |
| repair_axil_regs | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) |
| repair_cache_controller | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) |
| repair_gearbox_16to12 | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) |
| repair_noc_router5 | 0/1 (0%) → 0/1 (0%) | 0/1 (0%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) |
| repair_popcount16 | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) |
| repair_rr_arbiter4 | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) |
| repair_secded_ecc | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) | 1/1 (100%) → 1/1 (100%) |

Per-task cells: accepted on the first attempt → accepted within the turn budget. Accepted means every hidden test passed, the design synthesized without latches, and the formal check passed where enabled. Commit 96a0371; Yosys 0.33 (git sha1 2584903a060).

**WARNING:** **Inconclusive attempts: 1** (the grader could not decide, e.g. a tool hit its time limit; these count as not accepted). Check the per-arm rows below.

**Errored episodes: 0** (e.g. API errors; counted as unsolved).

- claude-haiku-5-5, feedback full: 1 inconclusive, 0 errored

### Front-end and resource failures by arm

| Model | Feedback | Front-end failures | Resource failures |
|---|---|---:|---:|
| claude-haiku-5-5 | full | 0 | 1 |
| claude-haiku-5-5 | none | 0 | 0 |
| claude-sonnet-5-5 | full | 0 | 0 |
| claude-sonnet-5-5 | none | 0 | 0 |

### Acceptance by task kind

| Model | Feedback | Kind | Episodes (errors) | First attempt | Within turn budget |
|---|---|---|---:|---:|---:|
| claude-haiku-5-5 | full | repair | 8 (0) | 7/8 | 7/8 |
| claude-haiku-5-5 | none | repair | 8 (0) | 7/8 | 8/8 |
| claude-sonnet-5-5 | full | repair | 8 (0) | 8/8 | 8/8 |
| claude-sonnet-5-5 | none | repair | 8 (0) | 8/8 | 8/8 |

### Repair edit size

| Model | Feedback | All graded attempts | Accepted attempts |
|---|---|---:|---:|
| claude-haiku-5-5 | full | 11.5 (n=10) | 10 (n=7) |
| claude-haiku-5-5 | none | 11 (n=9) | 10.5 (n=8) |
| claude-sonnet-5-5 | full | 4 (n=8) | 4 (n=8) |
| claude-sonnet-5-5 | none | 4 (n=8) | 4 (n=8) |

Cells show median lines changed from the starter (n = attempts with an edit count). Zero is included. Each feedback arm counts its shared first submission once. Accepted attempts satisfied the grading checks.

### Tokens per model

| Model | API calls | Input tokens | Output tokens (thinking included) |
|---|---:|---:|---:|
| claude-haiku-5-5 | 11 | 68,285 | 41,757 |
| claude-sonnet-5-5 | 8 | 24,773 | 13,675 |

Cost = input tokens x input price + output tokens x output price; check the current prices at https://platform.claude.com/docs/en/about-claude/pricing.

### Paired outcomes (same first attempt in both arms)

| Model | Episodes | Solved in both | Only full | Only none | In neither | Errored | Informative | Discordant | Exact McNemar p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 | 8 | 7 | 0 | 1 | 0 | 0 | 1 | 1 | 1.0 |
| claude-sonnet-5-5 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 1.0 |

### Paired outcomes by verification mode

| Model | Verification | Episodes | Solved in both | Only full | Only none | In neither | Errored | Informative | Discordant | Exact McNemar p |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 | Formal enabled | 8 | 7 | 0 | 1 | 0 | 0 | 1 | 1 | 1.0 |
| claude-sonnet-5-5 | Formal enabled | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 1.0 |

### Paired outcomes by task kind

| Model | Kind | Episodes | Solved in both | Only full | Only none | In neither | Errored |
|---|---|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 | repair | 8 | 7 | 0 | 1 | 0 | 0 |
| claude-sonnet-5-5 | repair | 8 | 8 | 0 | 0 | 0 | 0 |

Informative: first attempt not accepted (only these can differ between the arms). Discordant: solved in exactly one arm.
