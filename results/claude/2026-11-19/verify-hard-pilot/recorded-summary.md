## rtlgym eval

Models: claude-sonnet-5-5,claude-haiku-5-5. Tasks: verify_axi4_burst_slave,verify_cache_controller,verify_gearbox_16to12. 2 episode(s) per task, up to 1 attempts, paired=false, effort=model default, workers=2. Planned: at most 12 API calls.

| Arm | Episodes (errors) | Accepted on 1st attempt | 1st attempt passes tests | Accepted within N turns | Test escapes | Inconclusive | Mean turns | Grading p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 (feedback full) | 6 (0) | 2/6 (33%) | 2/6 (33%) | 2/6 (33%) (N=1) | 0 | 0 | 1.0 | 0.103 s / 14.315 s |
| claude-sonnet-5-5 (feedback full) | 6 (0) | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) (N=1) | 0 | 0 | 1.0 | 13.755 s / 33.558 s |

### Verification checker results

| Arm | Episodes (graded) | False alarms | Invalid | Inconclusive | Mutants caught | Mean family coverage | Mean reward |
|---|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 (feedback full) | 6 (6) | 0 | 4 | 0 | 28/80 | 33% | 0.3333 |
| claude-sonnet-5-5 (feedback full) | 6 (6) | 0 | 0 | 0 | 80/80 | 100% | 1.0 |

Each episode contributes its final checker. Mutant counts are checks across episodes. Family coverage weights mutation families equally. False alarms, invalid checkers, inconclusive grades and episodes with errors earn zero reward.

| Arm | Mean assertions | Mean state bits | Mean source bytes |
|---|---:|---:|---:|
| claude-haiku-5-5 (feedback full) | 2.5 | 19.17 | 2784.33 |
| claude-sonnet-5-5 (feedback full) | 12.67 | 96.67 | 4991.67 |

### Acceptance by verification mode

| Arm | Verification | Episodes (errors) | First attempt | Within turn budget |
|---|---|---:|---:|---:|
| claude-haiku-5-5 (feedback full) | Formal enabled | 6 (0) | 2/6 | 2/6 |
| claude-sonnet-5-5 (feedback full) | Formal enabled | 6 (0) | 6/6 | 6/6 |

| Task | claude-haiku-5-5 (feedback full) | claude-sonnet-5-5 (feedback full) |
|---|---:|---:|
| verify_axi4_burst_slave | 0/2 (0%) → 0/2 (0%) | 2/2 (100%) → 2/2 (100%) |
| verify_cache_controller | 0/2 (0%) → 0/2 (0%) | 2/2 (100%) → 2/2 (100%) |
| verify_gearbox_16to12 | 2/2 (100%) → 2/2 (100%) | 2/2 (100%) → 2/2 (100%) |

Per-task cells: accepted on the first attempt → accepted within the turn budget. A verification checker is accepted after passing the good-design checks and catching every included mutant. Commit 31bdbe9; Yosys 0.33 (git sha1 2584903a060).

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
| claude-sonnet-5-5 | full | verify | 6 (0) | 6/6 | 6/6 |

### Verification checker results

| Model | Feedback | Episodes (graded) | False alarms | Invalid | Inconclusive | Mutants caught | Mean family coverage | Mean reward |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| claude-haiku-5-5 | full | 6 (6) | 0 | 4 | 0 | 28/80 | 33.3% | 0.3333 |
| claude-sonnet-5-5 | full | 6 (6) | 0 | 0 | 0 | 80/80 | 100.0% | 1.0 |

Each episode contributes its final checker. Mutant counts are checks across episodes. Family coverage weights mutation families equally. False alarms, invalid checkers, inconclusive grades and episodes with errors earn zero reward.

| Model | Feedback | Mean assertions | Mean state bits | Mean source bytes |
|---|---|---:|---:|---:|
| claude-haiku-5-5 | full | 2.5 | 19.17 | 2784.33 |
| claude-sonnet-5-5 | full | 12.67 | 96.67 | 4991.67 |

### Tokens per model

| Model | API calls | Input tokens | Output tokens (thinking included) |
|---|---:|---:|---:|
| claude-haiku-5-5 | 6 | 30,576 | 142,797 |
| claude-sonnet-5-5 | 6 | 30,576 | 45,948 |

Cost = input tokens x input price + output tokens x output price; check the current prices at https://platform.claude.com/docs/en/about-claude/pricing.
