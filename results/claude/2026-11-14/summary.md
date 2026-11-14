## rtlgym eval

Models: claude-sonnet-5-5,claude-haiku-5-5. Tasks: all. 5 episode(s) per task, up to 3 attempts, paired=true, effort=model default, workers=4. Planned: at most 600 API calls.

| Arm | Episodes (errors) | Accepted on 1st attempt | 1st attempt passes tests | Accepted within N turns | Test escapes | Inconclusive | Mean turns | Grading p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 (feedback full, paired) | 60 (0) | 54/60 (90%) | 59/60 (98%) | 58/60 (97%) (N=3) | 0 | 1 | 1.133 | 1.224 s / 63.093 s |
| claude-haiku-5-5 (feedback none, paired) | 60 (0) | 54/60 (90%) | 59/60 (98%) | 54/60 (90%) (N=3) | 0 | 1 | 1.2 | 0.939 s / 87.63 s |
| claude-sonnet-5-5 (feedback full, paired) | 60 (0) | 50/60 (83%) | 57/60 (95%) | 60/60 (100%) (N=3) | 0 | 1 | 1.2 | 1.619 s / 68.905 s |
| claude-sonnet-5-5 (feedback none, paired) | 60 (0) | 50/60 (83%) | 57/60 (95%) | 57/60 (95%) (N=3) | 0 | 0 | 1.25 | 1.033 s / 46.912 s |

| Task | claude-haiku-5-5 (feedback full, paired) | claude-haiku-5-5 (feedback none, paired) | claude-sonnet-5-5 (feedback full, paired) | claude-sonnet-5-5 (feedback none, paired) |
|---|---:|---:|---:|---:|
| alu8 | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| axil_regs | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| crc32_stream | 4/5 (80%) → 5/5 (100%) | 4/5 (80%) → 4/5 (80%) | 2/5 (40%) → 5/5 (100%) | 2/5 (40%) → 5/5 (100%) |
| edge_detect | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| fifo_sync | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| mul_pipe3 | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| noc_router5 | 0/5 (0%) → 3/5 (60%) | 0/5 (0%) → 0/5 (0%) | 0/5 (0%) → 5/5 (100%) | 0/5 (0%) → 2/5 (40%) |
| popcount16 | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| rr_arbiter4 | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 3/5 (60%) → 5/5 (100%) | 3/5 (60%) → 5/5 (100%) |
| seq_detect_1011 | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| uart_tx | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |
| up_down_counter | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) | 5/5 (100%) → 5/5 (100%) |

Per-task cells: accepted on the first attempt → accepted within the turn budget. Accepted means every hidden test passed, the design synthesized without latches, and the formal check passed. Commit e7fa5e6; Yosys 0.33 (git sha1 2584903a060).

**WARNING:** **Inconclusive attempts: 3** (the grader could not decide, e.g. a tool hit its time limit; these count as not accepted). Check the per-arm rows below.

**Errored episodes: 0** (e.g. API errors; counted as unsolved).

- claude-haiku-5-5, feedback full: 1 inconclusive, 0 errored
- claude-haiku-5-5, feedback none: 1 inconclusive, 0 errored
- claude-sonnet-5-5, feedback full: 1 inconclusive, 0 errored

### Tokens per model

| Model | API calls | Input tokens | Output tokens (thinking included) |
|---|---:|---:|---:|
| claude-haiku-5-5 | 80 | 204,278 | 173,303 |
| claude-sonnet-5-5 | 87 | 156,029 | 122,187 |

Cost = input tokens x input price + output tokens x output price; check the current prices at https://platform.claude.com/docs/en/about-claude/pricing.

### Paired outcomes (same first attempt in both arms)

| Model | Episodes | Solved in both | Only full | Only none | In neither | Errored | Informative | Discordant | Exact McNemar p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 | 60 | 54 | 4 | 0 | 2 | 0 | 6 | 4 | 0.125 |
| claude-sonnet-5-5 | 60 | 57 | 3 | 0 | 0 | 0 | 10 | 3 | 0.25 |

Informative: first attempt not accepted (only these can differ between the arms). Discordant: solved in exactly one arm.
