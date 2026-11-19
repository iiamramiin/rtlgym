# November 17 verification pilot

Two samples on each of `verify_popcount16`, `verify_rr_arbiter4` and
`verify_fifo_sync`, per model: twelve one-shot submissions, default effort,
full feedback mode, four workers, commit `ba4f7ec`. Runs began November 17
Pacific time (November 18 UTC).

| Model | Accepted first | Checker-language rejections | Truncated | Mutants caught / assessed |
|---|---:|---:|---:|---:|
| Sonnet 5.5 | 2/6 | 4 | 0 | 22/22 |
| Haiku 5.5 | 2/6 | 4 | 0 | 22/22 |

Seven rejections used initialization forms the grader did not allow; one used
`$countones`. Those restrictions were absent from the specs. Rejected checkers'
mutant coverage and false alarms were unassessed. The accepted checkers raised
no false alarms. This primarily exposed checker-language restrictions.

The [later offline regrade](../verify-hard-regrade.md) accepted 11/12 after the
language fixes; one Sonnet FIFO proof was inconclusive in parallel. That exact
checker passed all correct designs and caught 14/14 mutants in an isolated
repeat with the same proof limit. The repeat does not replace the batch result.

The two original top-level JSON files are unchanged. The original top-level
`summary.md` is preserved byte for byte as `recorded-summary.md`; nested files
are omitted. This short summary does not replace archived grades.

| Archived file | SHA-256 of file bytes |
|---|---|
| `claude-haiku-5-5__full.json` | `53d45f4d03dab11504bf33cc5767e1db21f89a33f015788f5928ff5a41ebcedb` |
| `claude-sonnet-5-5__full.json` | `51b1e94bf266a1edab2b0e18e07a9583c8f6cd993c5ba96a13e9fc75e605561e` |
| `recorded-summary.md` | `27b6c5969dabc7fd058ceb2eb2ff08e3886eaa83ea46bd2d89a9f7431e184f58` |
