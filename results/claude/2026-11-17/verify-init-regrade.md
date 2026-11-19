# Offline regrade of the November 17 verification pilot

The pilot submitted two checkers per task and model for `verify_popcount16`, `verify_rr_arbiter4` and `verify_fifo_sync`, for twelve saved checkers. Each episode had one attempt, full feedback mode, default effort and four workers. The original grader was `ba4f7ec`.

The archive contains seven initialization rejections: five Verilator `initialstatic` forms from declaration initialization and two explicit `initial` blocks. A further Haiku arbiter checker was rejected at `$countones`. All four popcount checkers passed and caught 11/11 mutants. The original result was four accepted checkers and eight parser or checker-language rejections.

The saved source text was evaluated with `9c60484` without cache or model calls. The manifest records each exact UTF-8 SHA-256, model, task, sample, episode and the original JSON file's byte hash. Raw pilot files retain their archived verdicts.

The revised checker language admits constant initialization of private monitor state through declarations and initialization blocks, including bounded array initialization. It also supports initialized blocking monitor updates, bit-count helpers including `$countones`, and remainder by a positive constant power of two, as used by the pilot's `% 4` arbitration logic. Initial values are retained in both formal and simulation checkers.

Offline validation also found a signed array-index rendering defect. A narrowed two-bit index was regenerated as signed, turning array indices 2 and 3 into negative values. Both sample-2 FIFO sources passed independent native proofs and their purported counterexamples satisfied the literal queue contract. The final renderer restores the original array-index width, with original/regenerated regression checks, before producing the authoritative grades below.

| FIFO sample 2 | Original native proof | Corrected regenerated proof |
| --- | ---: | ---: |
| Haiku | pass, 7.029 s | pass, 1.641 s |
| Sonnet | pass, 12.075 s | pass, 3.974 s |

These diagnostic proofs used the same W=2, DEPTH=4 profile, 12 transitions plus the final observation and the published reset schedule. Their times describe individual reference proofs.

| Model | Archived accepted | Offline accepted | False alarms | Invalid | Inconclusive | Mutants caught / assessed | Mean weighted score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| claude-haiku-5-5 | 2/6 | 5/6 | 0 | 1 | 0 | 60/60 | 0.8333 |
| claude-sonnet-5-5 | 2/6 | 5/6 | 0 | 1 | 0 | 60/60 | 0.8333 |

The revised counts describe these twelve saved submissions under the revised checker language. They do not establish a feedback or retry advantage, since the pilot used one attempt per episode. Mutation counts sum across episodes, while the weighted score gives each mutation family equal weight. Any false alarm or inconclusive grade earns zero reward even if some mutants triggered assertions.

Both sample-1 FIFO checkers still lack complete constant initialization or reset of their private queue arrays. They remain invalid under the published monitor-state rule, with mutant coverage and false alarms unassessed.

Mutant coverage is assessed only after the correct-design gate succeeds. A rejected checker has unassessed coverage. A false alarm means an assertion failed on a correct design. Inconclusive checks remain unresolved.

| Model | Task | Sample / episode | SHA-256 | Archived status and reason | Offline status | Coverage old → new | False alarm old → new | Score old → new |
| --- | --- | --- | --- | --- | --- | ---: | --- | ---: |
| claude-haiku-5-5 | `verify_fifo_sync` | 1 / 1 | `dec6ecbd261f` | invalid: declaration initialization (Unsupported observer member initialstatic) | Invalid | not checked → not checked | not checked → not checked | 0.0000 → 0.0000 |
| claude-haiku-5-5 | `verify_fifo_sync` | 2 / 2 | `1e04acad8faf` | invalid: initial block (Unsupported observer member initial) | Accepted | not checked → 14/14 | not checked → no | 0.0000 → 1.0000 |
| claude-haiku-5-5 | `verify_popcount16` | 1 / 3 | `db03c4d65b0a` | pass: accepted | Accepted | 11/11 → 11/11 | no → no | 1.0000 → 1.0000 |
| claude-haiku-5-5 | `verify_popcount16` | 2 / 4 | `27f649c9da84` | pass: accepted | Accepted | 11/11 → 11/11 | no → no | 1.0000 → 1.0000 |
| claude-haiku-5-5 | `verify_rr_arbiter4` | 1 / 5 | `ab0ac4fd5a52` | invalid: declaration initialization (Unsupported observer member initialstatic) | Accepted | not checked → 12/12 | not checked → no | 0.0000 → 1.0000 |
| claude-haiku-5-5 | `verify_rr_arbiter4` | 2 / 6 | `b1c82f8c6936` | invalid: countones (Only pure integer cast and width system functions are supported) | Accepted | not checked → 12/12 | not checked → no | 0.0000 → 1.0000 |
| claude-sonnet-5-5 | `verify_fifo_sync` | 1 / 1 | `6ca4e1122d42` | invalid: declaration initialization (Unsupported observer member initialstatic) | Invalid | not checked → not checked | not checked → not checked | 0.0000 → 0.0000 |
| claude-sonnet-5-5 | `verify_fifo_sync` | 2 / 2 | `e043e626d951` | invalid: initial block (Unsupported observer member initial) | Accepted | not checked → 14/14 | not checked → no | 0.0000 → 1.0000 |
| claude-sonnet-5-5 | `verify_popcount16` | 1 / 3 | `1f5e67c0ffe8` | pass: accepted | Accepted | 11/11 → 11/11 | no → no | 1.0000 → 1.0000 |
| claude-sonnet-5-5 | `verify_popcount16` | 2 / 4 | `34dbbc14b239` | pass: accepted | Accepted | 11/11 → 11/11 | no → no | 1.0000 → 1.0000 |
| claude-sonnet-5-5 | `verify_rr_arbiter4` | 1 / 5 | `1b0fb6bdb08b` | invalid: declaration initialization (Unsupported observer member initialstatic) | Accepted | not checked → 12/12 | not checked → no | 0.0000 → 1.0000 |
| claude-sonnet-5-5 | `verify_rr_arbiter4` | 2 / 6 | `72971a371b45` | invalid: declaration initialization (Unsupported observer member initialstatic) | Accepted | not checked → 12/12 | not checked → no | 0.0000 → 1.0000 |

## Per-checker diagnostics

### claude-haiku-5-5, verify_fifo_sync, sample 1

Exact source SHA-256 `dec6ecbd261ff6040130d9f03404bb08cdafa1059df51a49bb19abf36bfbb29c`. Archived episode 1, turn 1 in `claude-haiku-5-5__full.json`.

Archived result was declaration initialization, score 0.0000. Offline result is invalid, mutant coverage not checked, false alarm not checked, score 0.0000.

Each persistent monitor register needs complete constant initialization or complete reset through the task reset signal

### claude-haiku-5-5, verify_fifo_sync, sample 2

Exact source SHA-256 `1e04acad8fafef6889b7dbb64e2bd506b100ddf199cea39d0e804a67883cb637`. Archived episode 2, turn 1 in `claude-haiku-5-5__full.json`.

Archived result was initial block, score 0.0000. Offline result is accepted, mutant coverage 14/14, false alarm no, score 1.0000.

| Target | Role | Formal | Simulation | Caught |
| --- | --- | --- | --- | --- |
| correct design 0 | positive | pass | passed | False |
| correct design 1 | positive | pass | passed | False |
| correct design 2 | positive | pass | passed | False |
| correct design 3 | positive | pass | passed | False |
| bug_full_flag | mutant | fail | passed | True |
| bug_fwft | mutant | fail | assertion failed | True |
| full_one_late | mutant | fail | passed | True |
| empty_one_early | mutant | fail | assertion failed | True |
| write_full_on_read | mutant | fail | passed | True |
| read_empty_on_write | mutant | fail | assertion failed | True |
| drop_write_pointer | mutant | fail | assertion failed | True |
| drop_read_pointer | mutant | fail | assertion failed | True |
| reset_count_one | mutant | fail | assertion failed | True |
| swap_write_index | mutant | fail | assertion failed | True |
| read_pointer_two | mutant | fail | assertion failed | True |
| write_zero | mutant | fail | assertion failed | True |
| write_msb_invert | mutant | fail | assertion failed | True |
| count_increment_on_read | mutant | fail | passed | True |

### claude-haiku-5-5, verify_popcount16, sample 1

Exact source SHA-256 `db03c4d65b0a9065d27d472878afa5f296d9c6808c82b2e4ae7fc84ca9fed8e6`. Archived episode 3, turn 1 in `claude-haiku-5-5__full.json`.

Archived result was accepted, score 1.0000. Offline result is accepted, mutant coverage 11/11, false alarm no, score 1.0000.

| Target | Role | Formal | Simulation | Caught |
| --- | --- | --- | --- | --- |
| correct design 0 | positive | pass | passed | False |
| correct design 1 | positive | pass | passed | False |
| bug_width | mutant | fail | passed | True |
| escape_rare_input | mutant | fail | passed | True |
| operator_xor | mutant | fail | assertion failed | True |
| operator_or | mutant | fail | assertion failed | True |
| offset_plus | mutant | fail | assertion failed | True |
| offset_minus | mutant | fail | assertion failed | True |
| threshold_eight | mutant | fail | assertion failed | True |
| drop_bit_zero | mutant | fail | assertion failed | True |
| duplicate_bit_two | mutant | fail | assertion failed | True |
| rare_zero | mutant | fail | passed | True |
| drop_bit_fifteen | mutant | fail | assertion failed | True |

### claude-haiku-5-5, verify_popcount16, sample 2

Exact source SHA-256 `27f649c9da848f265b5f2a8a0390d02de22d69bde55623fb078a5d7117f96152`. Archived episode 4, turn 1 in `claude-haiku-5-5__full.json`.

Archived result was accepted, score 1.0000. Offline result is accepted, mutant coverage 11/11, false alarm no, score 1.0000.

| Target | Role | Formal | Simulation | Caught |
| --- | --- | --- | --- | --- |
| correct design 0 | positive | pass | passed | False |
| correct design 1 | positive | pass | passed | False |
| bug_width | mutant | fail | passed | True |
| escape_rare_input | mutant | fail | passed | True |
| operator_xor | mutant | fail | assertion failed | True |
| operator_or | mutant | fail | assertion failed | True |
| offset_plus | mutant | fail | assertion failed | True |
| offset_minus | mutant | fail | assertion failed | True |
| threshold_eight | mutant | fail | assertion failed | True |
| drop_bit_zero | mutant | fail | assertion failed | True |
| duplicate_bit_two | mutant | fail | assertion failed | True |
| rare_zero | mutant | fail | passed | True |
| drop_bit_fifteen | mutant | fail | assertion failed | True |

### claude-haiku-5-5, verify_rr_arbiter4, sample 1

Exact source SHA-256 `ab0ac4fd5a52e220a5ead9dd692dd118984c3ab9b3b82bb3fcf17e53d3eb8dc6`. Archived episode 5, turn 1 in `claude-haiku-5-5__full.json`.

Archived result was declaration initialization, score 0.0000. Offline result is accepted, mutant coverage 12/12, false alarm no, score 1.0000.

| Target | Role | Formal | Simulation | Caught |
| --- | --- | --- | --- | --- |
| correct design 0 | positive | pass | passed | False |
| correct design 1 | positive | pass | passed | False |
| bug_fixed_priority | mutant | fail | assertion failed | True |
| bug_pointer_reset_on_idle | mutant | fail | passed | True |
| reset_priority_two | mutant | fail | passed | True |
| reset_grant_one | mutant | fail | assertion failed | True |
| pointer_plus_one | mutant | fail | assertion failed | True |
| grant_index_plus_one | mutant | fail | assertion failed | True |
| hold_idle_grant | mutant | fail | passed | True |
| cursor_on_all_only | mutant | fail | assertion failed | True |
| reverse_priority | mutant | fail | assertion failed | True |
| skip_requester_three | mutant | fail | assertion failed | True |
| all_requests_only | mutant | fail | assertion failed | True |
| grant_two_bits | mutant | fail | assertion failed | True |

### claude-haiku-5-5, verify_rr_arbiter4, sample 2

Exact source SHA-256 `b1c82f8c693656ed769201f3fc0df226cc59be942225253031706ad1efdd8a13`. Archived episode 6, turn 1 in `claude-haiku-5-5__full.json`.

Archived result was countones, score 0.0000. Offline result is accepted, mutant coverage 12/12, false alarm no, score 1.0000.

| Target | Role | Formal | Simulation | Caught |
| --- | --- | --- | --- | --- |
| correct design 0 | positive | pass | passed | False |
| correct design 1 | positive | pass | passed | False |
| bug_fixed_priority | mutant | fail | assertion failed | True |
| bug_pointer_reset_on_idle | mutant | fail | passed | True |
| reset_priority_two | mutant | fail | passed | True |
| reset_grant_one | mutant | fail | assertion failed | True |
| pointer_plus_one | mutant | fail | assertion failed | True |
| grant_index_plus_one | mutant | fail | assertion failed | True |
| hold_idle_grant | mutant | fail | passed | True |
| cursor_on_all_only | mutant | fail | assertion failed | True |
| reverse_priority | mutant | fail | assertion failed | True |
| skip_requester_three | mutant | fail | assertion failed | True |
| all_requests_only | mutant | fail | assertion failed | True |
| grant_two_bits | mutant | fail | assertion failed | True |

### claude-sonnet-5-5, verify_fifo_sync, sample 1

Exact source SHA-256 `6ca4e1122d42ce2ce1af14cadd1883b8b4ffddca71b8e2acb1d5027cbed900c9`. Archived episode 1, turn 1 in `claude-sonnet-5-5__full.json`.

Archived result was declaration initialization, score 0.0000. Offline result is invalid, mutant coverage not checked, false alarm not checked, score 0.0000.

Each persistent monitor register needs complete constant initialization or complete reset through the task reset signal

### claude-sonnet-5-5, verify_fifo_sync, sample 2

Exact source SHA-256 `e043e626d951274682dd3f2edb92f9dea6894dc50c7d650421223d3b3f6a0648`. Archived episode 2, turn 1 in `claude-sonnet-5-5__full.json`.

Archived result was initial block, score 0.0000. Offline result is accepted, mutant coverage 14/14, false alarm no, score 1.0000.

| Target | Role | Formal | Simulation | Caught |
| --- | --- | --- | --- | --- |
| correct design 0 | positive | pass | passed | False |
| correct design 1 | positive | pass | passed | False |
| correct design 2 | positive | pass | passed | False |
| correct design 3 | positive | pass | passed | False |
| bug_full_flag | mutant | fail | passed | True |
| bug_fwft | mutant | fail | assertion failed | True |
| full_one_late | mutant | fail | passed | True |
| empty_one_early | mutant | fail | assertion failed | True |
| write_full_on_read | mutant | fail | passed | True |
| read_empty_on_write | mutant | fail | assertion failed | True |
| drop_write_pointer | mutant | fail | assertion failed | True |
| drop_read_pointer | mutant | fail | assertion failed | True |
| reset_count_one | mutant | fail | assertion failed | True |
| swap_write_index | mutant | fail | assertion failed | True |
| read_pointer_two | mutant | fail | assertion failed | True |
| write_zero | mutant | fail | assertion failed | True |
| write_msb_invert | mutant | fail | assertion failed | True |
| count_increment_on_read | mutant | fail | passed | True |

### claude-sonnet-5-5, verify_popcount16, sample 1

Exact source SHA-256 `1f5e67c0ffe875165b8eac66f5a543e99abc3ad64271be46e47e8dcc4ff3f8fe`. Archived episode 3, turn 1 in `claude-sonnet-5-5__full.json`.

Archived result was accepted, score 1.0000. Offline result is accepted, mutant coverage 11/11, false alarm no, score 1.0000.

| Target | Role | Formal | Simulation | Caught |
| --- | --- | --- | --- | --- |
| correct design 0 | positive | pass | passed | False |
| correct design 1 | positive | pass | passed | False |
| bug_width | mutant | fail | passed | True |
| escape_rare_input | mutant | fail | passed | True |
| operator_xor | mutant | fail | assertion failed | True |
| operator_or | mutant | fail | assertion failed | True |
| offset_plus | mutant | fail | assertion failed | True |
| offset_minus | mutant | fail | assertion failed | True |
| threshold_eight | mutant | fail | assertion failed | True |
| drop_bit_zero | mutant | fail | assertion failed | True |
| duplicate_bit_two | mutant | fail | assertion failed | True |
| rare_zero | mutant | fail | passed | True |
| drop_bit_fifteen | mutant | fail | assertion failed | True |

### claude-sonnet-5-5, verify_popcount16, sample 2

Exact source SHA-256 `34dbbc14b23931946284808598604490d9bebf732b95e4bd8280689f8336cbef`. Archived episode 4, turn 1 in `claude-sonnet-5-5__full.json`.

Archived result was accepted, score 1.0000. Offline result is accepted, mutant coverage 11/11, false alarm no, score 1.0000.

| Target | Role | Formal | Simulation | Caught |
| --- | --- | --- | --- | --- |
| correct design 0 | positive | pass | passed | False |
| correct design 1 | positive | pass | passed | False |
| bug_width | mutant | fail | passed | True |
| escape_rare_input | mutant | fail | passed | True |
| operator_xor | mutant | fail | assertion failed | True |
| operator_or | mutant | fail | assertion failed | True |
| offset_plus | mutant | fail | assertion failed | True |
| offset_minus | mutant | fail | assertion failed | True |
| threshold_eight | mutant | fail | assertion failed | True |
| drop_bit_zero | mutant | fail | assertion failed | True |
| duplicate_bit_two | mutant | fail | assertion failed | True |
| rare_zero | mutant | fail | passed | True |
| drop_bit_fifteen | mutant | fail | assertion failed | True |

### claude-sonnet-5-5, verify_rr_arbiter4, sample 1

Exact source SHA-256 `1b0fb6bdb08b45740d20edc84f367aa023f613fa049b49938ccb6340ba88f392`. Archived episode 5, turn 1 in `claude-sonnet-5-5__full.json`.

Archived result was declaration initialization, score 0.0000. Offline result is accepted, mutant coverage 12/12, false alarm no, score 1.0000.

| Target | Role | Formal | Simulation | Caught |
| --- | --- | --- | --- | --- |
| correct design 0 | positive | pass | passed | False |
| correct design 1 | positive | pass | passed | False |
| bug_fixed_priority | mutant | fail | assertion failed | True |
| bug_pointer_reset_on_idle | mutant | fail | passed | True |
| reset_priority_two | mutant | fail | passed | True |
| reset_grant_one | mutant | fail | assertion failed | True |
| pointer_plus_one | mutant | fail | assertion failed | True |
| grant_index_plus_one | mutant | fail | assertion failed | True |
| hold_idle_grant | mutant | fail | passed | True |
| cursor_on_all_only | mutant | fail | assertion failed | True |
| reverse_priority | mutant | fail | assertion failed | True |
| skip_requester_three | mutant | fail | assertion failed | True |
| all_requests_only | mutant | fail | assertion failed | True |
| grant_two_bits | mutant | fail | assertion failed | True |

### claude-sonnet-5-5, verify_rr_arbiter4, sample 2

Exact source SHA-256 `72971a371b459baa1da3d04e037d77e57edaaab750c83e160c63737e614ceff1`. Archived episode 6, turn 1 in `claude-sonnet-5-5__full.json`.

Archived result was declaration initialization, score 0.0000. Offline result is accepted, mutant coverage 12/12, false alarm no, score 1.0000.

| Target | Role | Formal | Simulation | Caught |
| --- | --- | --- | --- | --- |
| correct design 0 | positive | pass | passed | False |
| correct design 1 | positive | pass | passed | False |
| bug_fixed_priority | mutant | fail | assertion failed | True |
| bug_pointer_reset_on_idle | mutant | fail | passed | True |
| reset_priority_two | mutant | fail | passed | True |
| reset_grant_one | mutant | fail | assertion failed | True |
| pointer_plus_one | mutant | fail | assertion failed | True |
| grant_index_plus_one | mutant | fail | assertion failed | True |
| hold_idle_grant | mutant | fail | passed | True |
| cursor_on_all_only | mutant | fail | assertion failed | True |
| reverse_priority | mutant | fail | assertion failed | True |
| skip_requester_three | mutant | fail | assertion failed | True |
| all_requests_only | mutant | fail | assertion failed | True |
| grant_two_bits | mutant | fail | assertion failed | True |

## Validation

Ruff is clean. All 452 pytest tests passed in 227.68 seconds. An uncached baseline with four workers graded all 29 tasks and 159 candidates in 97.9 seconds. All 159 stable result rows match the prior artifact, covering 142 design/repair rows and 17 verification rows, including coverage and target verdicts. Timing and diagnostic trace text are excluded from this comparison. The regression suite checks zero and nonzero initialization, original and regenerated native simulation/formal agreement, four-state bit-count helpers, cache isolation, and the parser rejection boundaries.

The prior baseline artifact SHA-256 is `b92957372ea5f6814d06a57bf1ae7ad6d76aa1431f1c67206da6491fc85c4848`. The final baseline artifact SHA-256 is `86e2429b8dea298012312dda0a79af78e9943efa98d237f61116e09fd720a85c`. Working evidence is `verify-baselines-committed.json`, `verify-init-baselines-final.json` and `verify-init-report/baseline-final-comparison.json` under `C:\Users\rajae\OneDrive\Documents\ChatGPT\Resume`.

## Reproduction and limits

The working exact-source manifest and grader result JSONL remain under `C:\Users\rajae\OneDrive\Documents\ChatGPT\Resume\verify-init-report`, as `verify-pilot-checkers.json` and `grades-final.jsonl`. The report join requires every saved coordinate and hash to match, and exactly one offline result for each task/source pair.

Sources are the top-level JSON files in `E:\11__my_github_repo\rtlgym_results\26_11_17__run1`. The source file hashes are recorded in the manifest. No raw pilot JSON was rewritten or copied into the repository for this report.

Two-state `bit` declarations are excluded from the checker subset because preserving their X/Z-to-zero coercion needs separate lowering. This restriction affects none of the twelve saved checkers. Ambiguous compiler reductions that discard array-address arithmetic are also rejected when the original expression cannot be preserved. Checker cache version 2 is separate from design/repair grader version 9.

| Original pilot file | File SHA-256 |
| --- | --- |
| `claude-haiku-5-5__full.json` | `53d45f4d03dab11504bf33cc5767e1db21f89a33f015788f5928ff5a41ebcedb` |
| `claude-sonnet-5-5__full.json` | `51b1e94bf266a1edab2b0e18e07a9583c8f6cd993c5ba96a13e9fc75e605561e` |
