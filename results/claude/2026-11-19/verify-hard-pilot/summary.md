# November 19 harder verification pilot

Two samples on each of `verify_axi4_burst_slave`, `verify_cache_controller` and
`verify_gearbox_16to12`, per model: twelve one-shot submissions, default effort,
full feedback mode, two workers, commit `31bdbe9`.

| Model | Accepted first | Truncated | Other invalid checkers | Mutants caught / assessed |
|---|---:|---:|---:|---:|
| Sonnet 5.5 | 6/6 | 0 | 0 | 80/80 |
| Haiku 5.5 | 2/6 | 4 | 0 | 28/28 |

Sonnet caught every admitted mutant in both samples on all three tasks, with
no false alarms on the supplied correct designs. Haiku's two gearbox checkers
also caught every mutant without false alarms. Its four AXI/cache replies each
hit 32,000 output tokens without a complete extracted code block. These are
reported as **truncated**, rather than checker errors; acceptance and reward
remain zero. Their coverage and false alarms were not assessed. The unchanged
raw JSON and recorded summary contain the original `invalid` labels.

This small pilot does not establish a feedback effect or measure checker
completeness beyond the published bounded profiles and mutant corpus. At this
size, Sonnet saturates these verification tasks; Haiku's four cut-off replies
do not establish that its completed checkers would fail.

The two original top-level JSON files are unchanged. The original top-level
`summary.md` is preserved byte for byte as `recorded-summary.md`; nested files
are omitted. No source was regraded for this reporting change.

| Archived file | SHA-256 of file bytes |
|---|---|
| `claude-haiku-5-5__full.json` | `bce38eb1600895a7f8343551a6cf3c0c6ff51155eaa0ef3561f597e647100bfc` |
| `claude-sonnet-5-5__full.json` | `13f475b50fe297148fe53b0817021ab84059329b65ea7c6ec169ee16d05fdecf` |
| `recorded-summary.md` | `b886c7ea404f79fc4e65834d80e15863a83b2c0eba48ebf9358ee44c379a2ffb` |
