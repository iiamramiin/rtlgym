| Model | Feedback | Episodes (errors) | First attempt (95% CI) | Within N turns (95% CI) | Mean best score | Truncated | Test escapes | N (turns) | Settings |
|---|---|---|---|---|---|---|---|---|---|
| llama3.1:8b | full | 36 (0) | 4/36 [3.1%, 26.1%] | 6/36 [6.4%, 32.8%] | 0.288 | 0 | 0 | 3 | think off, num_ctx=8192, num_predict=8192, seed=20261122, Q4_K_M, paired |
| llama3.1:8b | none | 36 (0) | 4/36 [3.1%, 26.1%] | 7/36 [8.2%, 36.0%] | 0.297 | 0 | 0 | 3 | think off, num_ctx=8192, num_predict=8192, seed=20261122, Q4_K_M, paired |

Intervals are exact 95% Clopper–Pearson binomial bounds, separately for each arm; errors remain in the denominator. These pooled-task intervals describe this sample and do not establish generalization to new task families.

| Model | Paired episodes | Both | Only full | Only none | Neither | Errored | Informative | Discordant | Exact McNemar p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| llama3.1:8b | 36 | 6 | 0 | 1 | 29 | 0 | 32 | 1 | 1 |

McNemar uses the discordant full/none pairs within each model. Shared first attempts are not independent observations.

| Task | llama3.1:8b / full | llama3.1:8b / none |
|---|---:|---:|
| alu8 | 0/3 → 0/3 | 0/3 → 0/3 |
| axil_regs | 0/3 → 0/3 | 0/3 → 0/3 |
| crc32_stream | 0/3 → 0/3 | 0/3 → 0/3 |
| edge_detect | 3/3 → 3/3 | 3/3 → 3/3 |
| fifo_sync | 0/3 → 0/3 | 0/3 → 0/3 |
| mul_pipe3 | 0/3 → 0/3 | 0/3 → 0/3 |
| noc_router5 | 0/3 → 0/3 | 0/3 → 0/3 |
| popcount16 | 0/3 → 0/3 | 0/3 → 1/3 |
| rr_arbiter4 | 0/3 → 0/3 | 0/3 → 0/3 |
| seq_detect_1011 | 0/3 → 0/3 | 0/3 → 0/3 |
| uart_tx | 0/3 → 0/3 | 0/3 → 0/3 |
| up_down_counter | 1/3 → 3/3 | 1/3 → 3/3 |

Per-task cells: accepted first → accepted within the turn budget.

| Model | Unique calls | Mean seconds per reply |
|---|---:|---:|
| llama3.1:8b | 160 | 143.71 |
