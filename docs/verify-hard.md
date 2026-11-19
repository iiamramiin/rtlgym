# Verification tasks with behavioral freedom

This change permits arbitrary initial private monitor storage, accepts
power-of-two constant remainders as array indices, and adds three verification
tasks with several legal timing schedules. No paid model calls were made.
The tasks require transaction or stream checks rather than an exact copy of one
implementation's ready/valid schedule. Their empirical difficulty is not yet known.

## Tasks and measured grading time

| Task | Reduced formal profile | Deliberate freedom | Mutants / families | Whole grade time |
| --- | --- | --- | ---: | --- |
| `verify_axi4_burst_slave` | 8 transitions; ADDR_W=3, ID_W=1, LEN_W=1 | One-cycle ready bubbles, delayed B/R offers, inactive payloads | 12 / 6 | 41.811 s |
| `verify_cache_controller` | 12 transitions; DATA_W=2, TAG_W=1, INDEX_W=1 | Hit/miss offer latency, rearming delay, inactive payloads | 14 / 6 | 16.750 s |
| `verify_gearbox_16to12` | 12 transitions; UNIT_W=2 | Independent input/output offer bubbles, inactive output data | 14 / 7 | 8.368 s |

Each task adds one final observation after its last transition and supplies four
correct designs, including its reference. Times above are complete hand-checker
grades from the November 18 uncached baseline with four workers. Both accepted AXI
fixtures were below 42 seconds; cache was below 17 seconds. These measurements
do not bound the difficulty of an arbitrary submitted checker.

AXI has a 240-second grading tool budget per attempt. Cache has 90 seconds and
gearbox has 60 seconds. Exhaustion is inconclusive, earns zero and is not cached.
The budget covers EDA tool calls;
Python preparation and cleanup can add overhead. The original three verification
tasks retain their existing limits.

## Grading budget headroom

On November 19, 2026, all 27 verification baseline candidates ran uncached
with four workers restricted to two CPUs (`taskset -c 0,1`). Every fixture
had its expected classification. The table uses the slower accepted reference
or good-checker grade for each task, including simulation and all formal gates.

| Task | Slowest accepted grade | Overall budget | Headroom |
| --- | ---: | ---: | ---: |
| `verify_axi4_burst_slave` | 71.017 s | 240 s | 3.38x |
| `verify_cache_controller` | 27.535 s | 90 s | 3.27x |
| `verify_fifo_sync` | 21.632 s | No aggregate cap | Uncapped |
| `verify_gearbox_16to12` | 13.771 s | 60 s | 4.36x |
| `verify_popcount16` | 2.169 s | No aggregate cap | Uncapped |
| `verify_rr_arbiter4` | 5.874 s | No aggregate cap | Uncapped |

Headroom is the overall budget divided by a complete checker grade. The
original three verification tasks do not set `max_grading_s`, so they have
no aggregate deadline. Individual proof limits remain unchanged (10 seconds
for cache, 15 seconds for the other tasks); they are separate from this ratio.
The headroom baseline evidence is kept outside the repository.

Every finite overall budget has at least 3x measured headroom. The chosen
budgets are 240 seconds for AXI and 90 seconds for cache; gearbox retains
60 seconds.

## Checker language fixes

Module-scope private registers and arrays may be uninitialized or only partially
initialized. Their unspecified bits remain arbitrary in formal analysis. The
grader does not fill them with zero or impose an undocumented reset requirement.
A checker that reads such storage before its value is established must still
pass for every possible initial value; otherwise the correct-design gate produces
a false alarm. Guarded queue storage can therefore be sound without clearing the
entire queue on reset.

This relaxation does not remove definite assignment for per-activation scratch
variables or function locals. Clocked temporaries must be assigned before use,
functions cannot retain hidden history between calls, and the existing single
writer, incomplete combinational assignment, native syntax and execution limits
remain. Constant declaration initialization and constant-only initialization
blocks continue to work. Initialization affects checker storage, not the DUT.

`mem[ptr % 4]` is accepted alongside `mem[ptr[1:0]]` when its native semantics meet
the supported remainder rule: a positive constant power-of-two divisor. Verilator
can discard remainder arithmetic while reducing an array address. A trusted
identity helper places the complete expression in a width-preserving native
argument context, and the rewritten artifact is parsed again. The renderer removes
only that trusted helper and checks that significant address bits were retained.
It does not guess missing arithmetic from the narrowed index or parse a replacement
expression itself. Signed negative indices, explicit slices and out-of-range
behavior require native/generated parity checks.

Native, protected and regenerated observers agree in simulation, including
X/Z operands and negative/out-of-range indices. Separate native Yosys proofs
cover the two-state formal semantics of signed/unsigned remainder, explicit
casts, nested indices, reset loops and function scope.
Reserved helper names, escaped collisions, invalid divisors and over-wide
indices are rejected. Both native parses share the published 15-second budget.
A 1,100-level array expression exposed a validation recursion crash during review;
the native tree now has a documented 128-level nesting limit and a regression.
Signed multiplication is also preserved through native XML rendering.

Checker cache version is **3**; design/repair grader version remains **9**.
The legacy design and repair system prompt retains its original hash and text.

## What the new contracts check

AXI uses the full five-channel interface with a small two-word memory and one-
or two-beat bursts. Its checker tracks accepted descriptors, byte strobes,
WLAST errors, IDs, burst order, error responses and data snapshots. Read and write
traffic can overlap. Offered responses must remain stable through backpressure,
but the checker allows the published ready and response delays. Reset suppresses
all three ready outputs. An exact always-ready checker fails on a legal throttled
design. The correct timing variants share the parent's functional core.

Cache uses two direct-mapped lines, two words per line and two possible tags.
It checks hit/miss classification, request addresses, refill word selection,
replacement tags, invalidation and the single-outstanding-transaction rule.
Memory requests and CPU responses may be offered after the published local delay;
external memory or CPU backpressure has no completion deadline. Correct designs
vary hit latency, miss-request latency and return-to-idle behavior. Inactive
payload values are not part of the contract.

Gearbox checks conservation and order of a stream of four-unit inputs and
three-unit outputs in an eight-unit buffer. Simultaneous transfers remove output
units before appending input units. Independent one-observation offer bubbles are
legal on either side; two consecutive eligible bubbles are not. A stalled offer
must keep its valid and payload stable. The two-bit-unit profile preserves the
4:3 conversion ratio but is smaller than the production-width namesake.

## Corpus qualification and limitations

The three frozen manifests contain 40 admitted mutants across 6, 6 and 7 families.
Operators and source hashes are recorded. Admission checks native compilation,
the exact interface and a bounded difference from the reference; pairwise bounded
comparisons remove behaviorally equivalent mutants. The hand-written contract
checker must also reject every admitted mutant and accept every supplied correct
design. A difference caused only by a permitted timing choice is not a bug.
Distinguishing witnesses demonstrate that the correct variants exercise freedom.

These are bounded results for published reduced profiles, not unbounded proofs
or signoff. Correct alternatives and mutants reuse implementation templates, so
shared mistakes remain possible. The corpus is public and is a development
fixture; it is not a private, held-out evaluation. Difficulty for either model must be measured by the proposed pilot. A cycle-exact
checker can be rejected for overconstraint even when its functional model is right.

## Integrated validation and saved pilot regrade

The functional commits are `cfb5204` (verifier), `e98ea09` (AXI), `fed6b2e`
(cache) and `703f11b` (gearbox), based on `main` at `70c1b26`. Numbered local
patches continue at 0029. No push or paid model call was made.

- Ruff is clean; **493 pytest tests passed in 255.00 s**.
- All **169 candidates across 32 tasks** ran uncached with four workers in
  **136.7 s**. The ten added checker fixtures have their expected classifications:
  complete checkers pass, cycle-exact/idle-payload overconstraints false-alarm,
  and the no-assertion fixture is invalid.
- All **159 existing rows match** their saved results, including scores,
  acceptance, formal verdicts, coverage, family counts, state counts, PPA fields
  and tool versions. Timing and diagnostic trace text are excluded.
- The baseline artifact SHA-256 is `e1fe450e50ebfebc6a60abb499bf37555d2ebbd7c886ca94364faa1660bbf861`;
  the prior artifact SHA-256 is `86e2429b8dea298012312dda0a79af78e9943efa98d237f61116e09fd720a85c`.
  The baseline artifacts and comparison evidence are kept outside the repository.

The exact twelve saved pilot sources were regraded without model calls or cache.
The final parallel batch has **11 accepted, one inconclusive, no syntax
rejections and no observed false alarms**. The two sample-1 FIFO checkers no
longer fail an initialization rule. Sonnet's FIFO sample 1 timed out on one
correct-design proof; its isolated repeat passed all correct designs and caught
14/14 at the unchanged limit. The repeat is recorded separately and does not
replace the batch acceptance rate. Per-checker results and exact-source hashes
are in [the regrade report](../results/claude/2026-11-17/verify-hard-regrade.md).

File purposes: `rtlgym/verify_syntax.py` validates and lowers the checker subset;
`rtlgym/verify.py` and `tools.py` apply optional grading budgets and parameterize
DUTs before hierarchy pruning. The verification prompt and all six task specs
publish the same rules. Each new task includes its checker, correct variants,
mutants and frozen manifest; `scripts/generate_verify_*.py` regenerates and
qualifies the corpora. Tests cover soundness, overconstraint, language semantics,
resource handling and legacy behavior.

## Proposed paid pilot: new tasks only

Use three tasks, two samples per task, two models, one attempt, default effort and
one worker: **12 model calls, six per model**. This is not a paired experiment and
cannot measure feedback or retry benefit. The 32,000-token reply limit includes
thinking. Omit `--effort` to retain the model's default. These commands are a plan;
they were not executed during this local implementation.

```bash
python -m rtlgym run --agent claude --model claude-sonnet-5-5 \
  --tasks verify_axi4_burst_slave,verify_cache_controller,verify_gearbox_16to12 \
  --samples 2 --max-turns 1 --workers 1 --max-tokens 32000 --no-cache \
  --out verify-hard-sonnet.json

python -m rtlgym run --agent claude --model claude-haiku-5-5 \
  --tasks verify_axi4_burst_slave,verify_cache_controller,verify_gearbox_16to12 \
  --samples 2 --max-turns 1 --workers 1 --max-tokens 32000 --no-cache \
  --out verify-hard-haiku.json

python -m rtlgym report verify-hard-sonnet.json verify-hard-haiku.json
```

At the November 18, 2026 rates verified from the
[official pricing page](https://platform.claude.com/docs/en/about-claude/pricing),
Sonnet is $2 input / $10 output per million tokens and Haiku is $0.10 / $0.50 for
these prompts below 100,000 tokens. Assume 10,000 input tokens per request and no
input caching or batch discount. Output figures below include thinking tokens.

| Scenario | Sonnet, six calls | Haiku, six calls | Total |
| --- | ---: | ---: | ---: |
| Expected, 8,000 output tokens per call | $0.600 | $0.030 | **$0.630** |
| Every reply reaches the 32,000-token output cap | $2.040 | $0.102 | **$2.142** |

These estimates exclude taxes and retries and assume the stated input length;
they are not an account spending limit. Record actual billable usage. Report
first-attempt acceptance, family-weighted coverage, false alarms, syntax rejection,
inconclusive/tool-limit counts and grading time separately. Inspect whether a
failed checker misunderstood the behavioral freedom before interpreting a model
difference or selecting a larger follow-up run.
