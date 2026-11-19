## rtlgym eval

Models: claude-sonnet-5-5,claude-haiku-5-5. Tasks: verify. 2 episode(s) per task, up to 1 attempts, paired=false, effort=model default, workers=4. Planned: at most 12 API calls.

| Arm | Episodes (errors) | Accepted on 1st attempt | 1st attempt passes tests | Accepted within N turns | Test escapes | Inconclusive | Mean turns | Grading p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 (feedback full) | 6 (0) | 2/6 (33%) | 2/6 (33%) | 2/6 (33%) (N=1) | 0 | 0 | 1.0 | 0.093 s / 1.558 s |
| claude-sonnet-5-5 (feedback full) | 6 (0) | 2/6 (33%) | 2/6 (33%) | 2/6 (33%) (N=1) | 0 | 0 | 1.0 | 0.093 s / 1.712 s |

### Verification checker results

| Arm | Episodes (graded) | False alarms | Invalid | Inconclusive | Mutants caught | Mean family coverage | Mean reward |
|---|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 (feedback full) | 6 (6) | 0 | 4 | 0 | 22/74 | 33% | 0.3333 |
| claude-sonnet-5-5 (feedback full) | 6 (6) | 0 | 4 | 0 | 22/74 | 33% | 0.3333 |

Each episode contributes its final checker. Mutant counts are checks across episodes. Family coverage weights mutation families equally. False alarms, invalid checkers, inconclusive grades and episodes with errors earn zero reward.

| Arm | Mean assertions | Mean state bits | Mean source bytes |
|---|---:|---:|---:|
| claude-haiku-5-5 (feedback full) | 0.5 | 0 | 1403.67 |
| claude-sonnet-5-5 (feedback full) | 0.5 | 0 | 1143.83 |

### Acceptance by verification mode

| Arm | Verification | Episodes (errors) | First attempt | Within turn budget |
|---|---|---:|---:|---:|
| claude-haiku-5-5 (feedback full) | Formal enabled | 6 (0) | 2/6 | 2/6 |
| claude-sonnet-5-5 (feedback full) | Formal enabled | 6 (0) | 2/6 | 2/6 |

| Task | claude-haiku-5-5 (feedback full) | claude-sonnet-5-5 (feedback full) |
|---|---:|---:|
| verify_fifo_sync | 0/2 (0%) → 0/2 (0%) | 0/2 (0%) → 0/2 (0%) |
| verify_popcount16 | 2/2 (100%) → 2/2 (100%) | 2/2 (100%) → 2/2 (100%) |
| verify_rr_arbiter4 | 0/2 (0%) → 0/2 (0%) | 0/2 (0%) → 0/2 (0%) |

Per-task cells: accepted on the first attempt → accepted within the turn budget. A verification checker is accepted after passing the good-design checks and catching every included mutant. Commit ba4f7ec; Yosys 0.33 (git sha1 2584903a060).

**Inconclusive attempts: 0** (the grader could not decide, e.g. a tool hit its time limit; these count as not accepted).

**Errored episodes: 0** (e.g. API errors; counted as unsolved).

### Front-end and resource failures by arm

| Model | Feedback | Front-end failures | Resource failures |
|---|---|---:|---:|
| claude-haiku-5-5 | full | 0 | 0 |
| claude-sonnet-5-5 | full | 0 | 0 |

### Icarus simulation front-end retries

| Model | Feedback | Compiled after sv2v |
|---|---|---:|
| claude-haiku-5-5 | full | 0 |
| claude-sonnet-5-5 | full | 0 |

### Acceptance by task kind

| Model | Feedback | Kind | Episodes (errors) | First attempt | Within turn budget |
|---|---|---|---:|---:|---:|
| claude-haiku-5-5 | full | verify | 6 (0) | 2/6 | 2/6 |
| claude-sonnet-5-5 | full | verify | 6 (0) | 2/6 | 2/6 |

### Verification checker results

| Model | Feedback | Episodes (graded) | False alarms | Invalid | Inconclusive | Mutants caught | Mean family coverage | Mean reward |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 | full | 6 (6) | 0 | 4 | 0 | 22/74 | 33.3% | 0.3333 |
| claude-sonnet-5-5 | full | 6 (6) | 0 | 4 | 0 | 22/74 | 33.3% | 0.3333 |

Each episode contributes its final checker. Mutant counts are checks across episodes. Family coverage weights mutation families equally. False alarms, invalid checkers, inconclusive grades and episodes with errors earn zero reward.

| Model | Feedback | Mean assertions | Mean state bits | Mean source bytes |
|---|---|---:|---:|---:|
| claude-haiku-5-5 | full | 0.5 | 0 | 1403.67 |
| claude-sonnet-5-5 | full | 0.5 | 0 | 1143.83 |

### Tokens per model

| Model | API calls | Input tokens | Output tokens (thinking included) |
|---|---:|---:|---:|
| claude-haiku-5-5 | 6 | 5,756 | 13,044 |
| claude-sonnet-5-5 | 6 | 5,756 | 5,108 |

Cost = input tokens x input price + output tokens x output price; check the current prices at https://platform.claude.com/docs/en/about-claude/pricing.
