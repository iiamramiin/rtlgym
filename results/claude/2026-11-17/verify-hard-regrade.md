# Offline regrade of the November 17 verification pilot

These are the same twelve saved one-shot submissions, two samples per task and model. Only the grader changed. No source was edited, no model was called and no result cache was used. The original top-level JSON files retain their archived verdicts.

Original `ba4f7ec`: 4/12 accepted; 44/44 mutants caught/assessed; 0 false alarms, 8 invalid, 0 inconclusive. `verify-init` (`9c60484`, checker grader 2): 10/12 accepted; 120/120 mutants caught/assessed; 0 false alarms, 2 invalid, 0 inconclusive. `verify-hard` (`cfb5204`, checker grader 3): 11/12 accepted; 134/134 mutants caught/assessed; 0 false alarms, 0 invalid, 1 inconclusive.

The new rule permits private module storage without reset or initialization. The native formal check quantifies over unspecified initial storage; it does not assume zero. A checker that relies on an unknown initial value still fails the correct-design gate. The two FIFO sample-1 submissions previously rejected for their private queue arrays were evaluated unchanged under this rule. Initialized values remain honored.

The renderer also accepts power-of-two remainder array indices such as `mem[ptr % 4]`. The three new harder task corpora are separate from this pilot and do not enter these counts.

## Per-checker results

Each version cell lists **status; mutants caught/total; false alarm; reward**. An invalid checker has unassessed coverage and false alarms, rather than measured zeros. A false alarm or inconclusive proof earns zero. Coverage is assessed only after all correct-design checks pass. Rewards weight mutation families equally.

| Model | Task / sample | Original `ba4f7ec` | `verify-init` `9c60484` | `verify-hard` `cfb5204` |
| --- | --- | --- | --- | --- |
| Haiku 5.5 | `verify_fifo_sync` / 1 | invalid; unassessed; unassessed; 0.0000 | invalid; unassessed; unassessed; 0.0000 | accepted; 14/14; no; 1.0000 |
| Haiku 5.5 | `verify_fifo_sync` / 2 | invalid; unassessed; unassessed; 0.0000 | accepted; 14/14; no; 1.0000 | accepted; 14/14; no; 1.0000 |
| Haiku 5.5 | `verify_popcount16` / 1 | accepted; 11/11; no; 1.0000 | accepted; 11/11; no; 1.0000 | accepted; 11/11; no; 1.0000 |
| Haiku 5.5 | `verify_popcount16` / 2 | accepted; 11/11; no; 1.0000 | accepted; 11/11; no; 1.0000 | accepted; 11/11; no; 1.0000 |
| Haiku 5.5 | `verify_rr_arbiter4` / 1 | invalid; unassessed; unassessed; 0.0000 | accepted; 12/12; no; 1.0000 | accepted; 12/12; no; 1.0000 |
| Haiku 5.5 | `verify_rr_arbiter4` / 2 | invalid; unassessed; unassessed; 0.0000 | accepted; 12/12; no; 1.0000 | accepted; 12/12; no; 1.0000 |
| Sonnet 5.5 | `verify_fifo_sync` / 1 | invalid; unassessed; unassessed; 0.0000 | invalid; unassessed; unassessed; 0.0000 | inconclusive; unassessed; unresolved; 0.0000 |
| Sonnet 5.5 | `verify_fifo_sync` / 2 | invalid; unassessed; unassessed; 0.0000 | accepted; 14/14; no; 1.0000 | accepted; 14/14; no; 1.0000 |
| Sonnet 5.5 | `verify_popcount16` / 1 | accepted; 11/11; no; 1.0000 | accepted; 11/11; no; 1.0000 | accepted; 11/11; no; 1.0000 |
| Sonnet 5.5 | `verify_popcount16` / 2 | accepted; 11/11; no; 1.0000 | accepted; 11/11; no; 1.0000 | accepted; 11/11; no; 1.0000 |
| Sonnet 5.5 | `verify_rr_arbiter4` / 1 | invalid; unassessed; unassessed; 0.0000 | accepted; 12/12; no; 1.0000 | accepted; 12/12; no; 1.0000 |
| Sonnet 5.5 | `verify_rr_arbiter4` / 2 | invalid; unassessed; unassessed; 0.0000 | accepted; 12/12; no; 1.0000 | accepted; 12/12; no; 1.0000 |

## Nonaccepted submissions in the parallel batch

- claude-sonnet-5-5, `verify_fifo_sync` sample 1: inconclusive.

## Exact-source provenance

The original top-level pilot JSON files are kept outside the repository. The join verifies each raw JSON byte hash, original episode/task/sample/turn, exact submitted UTF-8 source hash and archived verdict before joining both offline grades by task and full SHA-256. It requires exactly twelve unique coordinates and sources at every stage.

| Original pilot file | SHA-256 of file bytes |
| --- | --- |
| `claude-haiku-5-5__full.json` | `53d45f4d03dab11504bf33cc5767e1db21f89a33f015788f5928ff5a41ebcedb` |
| `claude-sonnet-5-5__full.json` | `51b1e94bf266a1edab2b0e18e07a9583c8f6cd993c5ba96a13e9fc75e605561e` |

| Model / task / sample | Exact submitted source SHA-256 |
| --- | --- |
| Haiku / `verify_fifo_sync` / 1 | `dec6ecbd261ff6040130d9f03404bb08cdafa1059df51a49bb19abf36bfbb29c` |
| Haiku / `verify_fifo_sync` / 2 | `1e04acad8fafef6889b7dbb64e2bd506b100ddf199cea39d0e804a67883cb637` |
| Haiku / `verify_popcount16` / 1 | `db03c4d65b0a9065d27d472878afa5f296d9c6808c82b2e4ae7fc84ca9fed8e6` |
| Haiku / `verify_popcount16` / 2 | `27f649c9da848f265b5f2a8a0390d02de22d69bde55623fb078a5d7117f96152` |
| Haiku / `verify_rr_arbiter4` / 1 | `ab0ac4fd5a52e220a5ead9dd692dd118984c3ab9b3b82bb3fcf17e53d3eb8dc6` |
| Haiku / `verify_rr_arbiter4` / 2 | `b1c82f8c693656ed769201f3fc0df226cc59be942225253031706ad1efdd8a13` |
| Sonnet / `verify_fifo_sync` / 1 | `6ca4e1122d42ce2ce1af14cadd1883b8b4ffddca71b8e2acb1d5027cbed900c9` |
| Sonnet / `verify_fifo_sync` / 2 | `e043e626d951274682dd3f2edb92f9dea6894dc50c7d650421223d3b3f6a0648` |
| Sonnet / `verify_popcount16` / 1 | `1f5e67c0ffe875165b8eac66f5a543e99abc3ad64271be46e47e8dcc4ff3f8fe` |
| Sonnet / `verify_popcount16` / 2 | `34dbbc14b23931946284808598604490d9bebf732b95e4bd8280689f8336cbef` |
| Sonnet / `verify_rr_arbiter4` / 1 | `1b0fb6bdb08b45740d20edc84f367aa023f613fa049b49938ccb6340ba88f392` |
| Sonnet / `verify_rr_arbiter4` / 2 | `72971a371b459baa1da3d04e037d77e57edaaab750c83e160c63737e614ceff1` |

The exact-source manifest and offline grading evidence are kept outside the repository. Raw pilot JSON was not rewritten or copied by this report.

| Working evidence | SHA-256 of file bytes |
| --- | --- |
| `verify-pilot-checkers.json` | `1792ed738ab290710145ae1359afa5121a18aeaeb9cdb7e8b950278aabda0c78` |
| `grades-final.jsonl` | `5eaa0c65888f6773c08ae33285b5f3bf1dd3261700d9997f449076731050e548` |
| `pilot-final.jsonl` | `6f60fdf1c6c5f74b14a3123c366ebc915ffda351aa708b95d01f7af19eb62a2f` |

These counts measure the saved submissions on the existing public, bounded mutation corpora. They establish neither a retry/feedback advantage nor performance on the new harder tasks. Correct-design acceptance is bounded to the published parameters, reset schedule and supplied legal implementations; it is not an unbounded proof of checker completeness.

## Isolated diagnostic repeat

The final batch ran alongside the full pytest suite. Sonnet FIFO sample 1 passed
its reference proof in 10.671 s, then hit the unchanged 15-second SAT limit on the
next correct design (16.491 s wall time). It was **inconclusive**, earned zero,
and was not cached. This was not a syntax rejection or an assertion failure.

After the test and baseline jobs finished, the exact same source was evaluated
once in isolation, uncached, with the same 15-second proof limit. It passed all
four correct designs, caught **14/14** mutants, raised no false alarms and earned
1.0 in **23.981 s** total. Its four positive proofs took 5.127, 5.975, 4.685
and 3.487 s. The repeat is diagnostic and **does not replace the parallel batch's
11/12 acceptance rate**. Runtime sensitivity remains; the proof limit was not
increased to resolve it.

The repeat has the same full source hash shown in the table above. Both the
parallel batch and isolated repeat are retained as working evidence.

- `pilot-parallel.jsonl`: SHA-256 `6f60fdf1c6c5f74b14a3123c366ebc915ffda351aa708b95d01f7af19eb62a2f`.
- `pilot-isolated.jsonl`: SHA-256 `5ab845fe7462e7fc0d8ffe07eb54213d406d38faacf703a9974d595b0c6bd556`.
