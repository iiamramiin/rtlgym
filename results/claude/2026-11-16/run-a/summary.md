## rtlgym eval

Models: claude-sonnet-5-5,claude-haiku-5-5. Tasks: popcount16,alu8,up_down_counter,edge_detect,seq_detect_1011,fifo_sync,rr_arbiter4,uart_tx,noc_router5,axil_regs,mul_pipe3,crc32_stream. 5 episode(s) per task, up to 3 attempts, paired=true, effort=model default, workers=4. Planned: at most 600 API calls.

| Arm | Episodes (errors) | Accepted on 1st attempt | 1st attempt passes tests | Accepted within N turns | Test escapes | Inconclusive | Mean turns | Grading p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 (feedback full, paired) | 60 (0) | 58/60 (97%) | 59/60 (98%) | 60/60 (100%) (N=3) | 0 | 1 | 1.033 | 1.329 s / 86.893 s |
| claude-haiku-5-5 (feedback none, paired) | 60 (0) | 58/60 (97%) | 59/60 (98%) | 58/60 (97%) (N=3) | 0 | 2 | 1.067 | 0.89 s / 63.295 s |
| claude-sonnet-5-5 (feedback full, paired) | 60 (0) | 51/60 (85%) | 54/60 (90%) | 60/60 (100%) (N=3) | 0 | 3 | 1.183 | 1.382 s / 83.36 s |
| claude-sonnet-5-5 (feedback none, paired) | 60 (0) | 51/60 (85%) | 54/60 (90%) | 56/60 (93%) (N=3) | 0 | 9 | 1.25 | 35.399 s / 134.863 s |

### Acceptance by verification mode

| Arm | Verification | Episodes (errors) | First attempt | Within turn budget |
|---|---|---:|---:|---:|
| claude-haiku-5-5 (feedback full, paired) | Formal enabled | 60 (0) | 58/60 | 60/60 |
| claude-haiku-5-5 (feedback none, paired) | Formal enabled | 60 (0) | 58/60 | 58/60 |
| claude-sonnet-5-5 (feedback full, paired) | Formal enabled | 60 (0) | 51/60 | 60/60 |
| claude-sonnet-5-5 (feedback none, paired) | Formal enabled | 60 (0) | 51/60 | 56/60 |

| Task | claude-haiku-5-5 (feedback full, paired) | claude-haiku-5-5 (feedback none, paired) | claude-sonnet-5-5 (feedback full, paired) | claude-sonnet-5-5 (feedback none, paired) |
|---|---:|---:|---:|---:|
| alu8 | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| axil_regs | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| crc32_stream | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| edge_detect | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| fifo_sync | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| mul_pipe3 | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 3/5 (60%) → 5/5 (100%) | 3/5 (60%) → 5/5 (100%) |
| noc_router5 | 3/5 (60%) → 5/5 (100%) | 3/5 (60%) → 3/5 (60%) | 0/5 (0%) → 5/5 (100%) | 0/5 (0%) → 1/5 (20%) |
| popcount16 | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| rr_arbiter4 | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 3/5 (60%) → 5/5 (100%) | 3/5 (60%) → 5/5 (100%) |
| seq_detect_1011 | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| uart_tx | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| up_down_counter | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |

Per-task cells: accepted on the first attempt → accepted within the turn budget. Accepted means every hidden test passed, the design synthesized without latches, and the formal check passed where enabled. Commit e12a9a3; Yosys 0.33 (git sha1 2584903a060).

**WARNING:** **Inconclusive attempts: 15** (the grader could not decide, e.g. a tool hit its time limit; these count as not accepted). Check the per-arm rows below.

**Errored episodes: 0** (e.g. API errors; counted as unsolved).

- claude-haiku-5-5, feedback full: 1 inconclusive, 0 errored
- claude-haiku-5-5, feedback none: 2 inconclusive, 0 errored
- claude-sonnet-5-5, feedback full: 3 inconclusive, 0 errored
- claude-sonnet-5-5, feedback none: 9 inconclusive, 0 errored

### Front-end and resource failures by arm

| Model | Feedback | Front-end failures | Resource failures |
|---|---|---:|---:|
| claude-haiku-5-5 | full | 0 | 1 |
| claude-haiku-5-5 | none | 0 | 2 |
| claude-sonnet-5-5 | full | 0 | 3 |
| claude-sonnet-5-5 | none | 0 | 9 |

### Tokens per model

| Model | API calls | Input tokens | Output tokens (thinking included) |
|---|---:|---:|---:|
| claude-haiku-5-5 | 66 | 100,647 | 136,804 |
| claude-sonnet-5-5 | 86 | 159,082 | 115,897 |

Cost = input tokens x input price + output tokens x output price; check the current prices at https://platform.claude.com/docs/en/about-claude/pricing.

### Paired outcomes (same first attempt in both arms)

| Model | Episodes | Solved in both | Only full | Only none | In neither | Errored | Informative | Discordant | Exact McNemar p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 | 60 | 58 | 2 | 0 | 0 | 0 | 2 | 2 | 0.5 |
| claude-sonnet-5-5 | 60 | 56 | 4 | 0 | 0 | 0 | 9 | 4 | 0.125 |

### Paired outcomes by verification mode

| Model | Verification | Episodes | Solved in both | Only full | Only none | In neither | Errored | Informative | Discordant | Exact McNemar p |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 | Formal enabled | 60 | 58 | 2 | 0 | 0 | 0 | 2 | 2 | 0.5 |
| claude-sonnet-5-5 | Formal enabled | 60 | 56 | 4 | 0 | 0 | 0 | 9 | 4 | 0.125 |

Informative: first attempt not accepted (only these can differ between the arms). Discordant: solved in exactly one arm.
