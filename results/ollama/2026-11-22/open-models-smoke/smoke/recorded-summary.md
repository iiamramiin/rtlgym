| Model | Feedback | Episodes (errors) | First attempt (95% CI) | Within N turns (95% CI) | Mean best score | Truncated | Test escapes | N (turns) | Settings |
|---|---|---|---|---|---|---|---|---|---|
| llama3.1:8b | full | 2 (0) | 1/2 [1.3%, 98.7%] | 1/2 [1.3%, 98.7%] | 0.500 | 0 | 0 | 3 | think off, num_ctx=8192, num_predict=8192, seed=20261122, Q4_K_M, paired |
| llama3.1:8b | none | 2 (0) | 1/2 [1.3%, 98.7%] | 1/2 [1.3%, 98.7%] | 0.500 | 0 | 0 | 3 | think off, num_ctx=8192, num_predict=8192, seed=20261122, Q4_K_M, paired |
| qwen3:14b | full | 2 (0) | 1/2 [1.3%, 98.7%] | 1/2 [1.3%, 98.7%] | 0.474 | 0 | 0 | 3 | think off, num_ctx=8192, num_predict=8192, seed=20261122, Q4_K_M, paired |
| qwen3:14b | none | 2 (0) | 1/2 [1.3%, 98.7%] | 1/2 [1.3%, 98.7%] | 0.474 | 0 | 0 | 3 | think off, num_ctx=8192, num_predict=8192, seed=20261122, Q4_K_M, paired |

Intervals are exact 95% Clopper–Pearson binomial bounds, separately for each arm; errors remain in the denominator. These pooled-task intervals describe this sample and do not establish generalization to new task families.

| Model | Paired episodes | Both | Only full | Only none | Neither | Errored | Informative | Discordant | Exact McNemar p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| llama3.1:8b | 2 | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 1 |
| qwen3:14b | 2 | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 1 |

McNemar uses the discordant full/none pairs within each model. Shared first attempts are not independent observations.

| Task | llama3.1:8b / full | llama3.1:8b / none | qwen3:14b / full | qwen3:14b / none |
|---|---:|---:|---:|---:|
| popcount16 | 0/1 → 0/1 | 0/1 → 0/1 | 1/1 → 1/1 | 1/1 → 1/1 |
| verify_popcount16 | 1/1 → 1/1 | 1/1 → 1/1 | 0/1 → 0/1 | 0/1 → 0/1 |

Per-task cells: accepted first → accepted within the turn budget.

| Model | Unique calls | Mean seconds per reply |
|---|---:|---:|
| llama3.1:8b | 6 | 115.38 |
| qwen3:14b | 6 | 311.42 |
