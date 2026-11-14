# rtlgym

**An RL environment and eval harness for LLM-generated RTL.**

An agent gets a natural-language hardware spec, writes SystemVerilog, and receives a
shaped reward computed by real open-source EDA tools:

| Stage | Tool | What it checks |
|---|---|---|
| Static checks | Python | forbidden constructs (`$finish`, file I/O, `` `include ``), right module name, size limit |
| Compile | Icarus Verilog 12 | the code parses and elaborates |
| Lint | Verilator 5 | warnings, plus simulation-only constructs such as `#` delays |
| Function | cocotb 2 + Icarus | **hidden** testbench with a Python reference model |
| Formal | Yosys SAT | equivalence with the reference design; returns a counterexample when they differ |
| Area/depth proxies | Yosys | generic-gate count (area proxy), logic depth (delay proxy), flops, inferred latches |

The environment is multi-turn: after each attempt the agent sees compiler errors, lint
warnings, the names and messages of failing hidden tests, a cycle-by-cycle
counterexample from the formal check, and its synthesis numbers next to the reference
design, and can try again.

```
spec.md ──► agent ──► RTL ──► static ─► compile ─┬─► lint   ──┐
   ▲                                             ├─► synth  ──┤
   │                                             ├─► tests  ──┼─► reward + feedback
   └──────────────── feedback ◄──────────────────┴─► formal ──┘
```

## Quick start

rtlgym runs on Linux (on Windows, use WSL). Install it from a clone: the tasks live
next to the package, not inside it.

```bash
sudo apt-get install -y iverilog verilator yosys        # Ubuntu 24.04
pip install -e ".[dev]"

python -m rtlgym list                                   # 8 tasks
python -m rtlgym score fifo_sync my_fifo.sv             # grade one file
python -m rtlgym baselines                              # grade every hand-written candidate
python -m rtlgym run --agent replay                     # multi-turn episodes, no API key needed
pytest -q                                               # 182 tests
```

## Using it as an RL environment

```python
from rtlgym import RTLEnv

env = RTLEnv(max_turns=3, reward_mode="improvement", feedback="full")
obs, info = env.reset(task_id="uart_tx")          # or reset(seed=0) for a random task
while True:
    action = policy(obs["spec"], obs["feedback"])   # any string containing a SystemVerilog module
    obs, reward, terminated, truncated, info = env.step(action)
    if terminated or truncated:
        break
```

- `step()` returns the Gymnasium 5-tuple. `info["eval"]` holds the full `EvalResult`
  (per-stage results, logs, gate counts, formal status and counterexample, timings).
- An episode ends when an attempt is **accepted**: every expected hidden test ran and
  passed, the design synthesizes without latches, its ports match the reference, and
  the formal check passed. A formal error or timeout, or a simulation that ended before
  every test reported, is **inconclusive**: not accepted, and never cached. The same
  predicate ends episodes, defines solve rates, and gates the area/depth bonus.
- `info` carries the full grading result for the trainer and for logging. A policy
  under evaluation should only see `obs`.
- `reward_mode="improvement"` pays only the gain over the best score so far, so the
  episode return equals the best score reached and re-submitting the same answer earns
  nothing. `reward_mode="score"` pays the raw score every turn.
- `feedback` is `"none"` (single-shot eval), `"summary"` (counts and status only), or
  `"full"`. Full feedback reveals failing test names, messages, and counterexamples,
  which is useful for training a repair loop but leaks information about the hidden
  checks; use `summary` or `none` for held-out evaluation.
- `use_formal=False` turns the formal check off, for ablations.

## Formal equivalence checking

Hidden tests sample behavior. The formal check covers every input: the candidate and
the reference are wired into a miter (same inputs, outputs compared) and Yosys's SAT
solver searches for any input sequence that makes an output differ.

- **Combinational designs** are proved exhaustively. For `popcount16`, that means all
  65,536 inputs.
- **Sequential designs** get a bounded model check: both designs start from the same
  all-zero state, reset is applied in cycle 1, and every input sequence is covered up
  to the depth set in `task.toml` (12 cycles for most tasks; 48 for `uart_tx`, enough
  for a full 40-cycle frame). Reset is held low after cycle 1, so behavior under a
  mid-run reset is left to the simulation tests. Parameterized designs can be checked
  at smaller parameter values (`fifo_sync` uses `W=2, DEPTH=4`) to keep the proof fast.
- When the designs differ, the agent gets the counterexample:

```
Formal: every hidden test passes, but the formal check found inputs where your design differs from the reference.
Counterexample:
  inputs[x=0xbeef]  reference[count=0xd]  yours[count=0xc]   <-- differs
```

That example is `popcount16/candidates/escape_rare_input.sv`: wrong for one input
value out of 65,536, so it passes all 500 random test vectors. Such a **test escape**
is exactly the failure a sampled-test reward misses, and a policy trained on that
reward would learn to exploit it.

## Reward

The reward is a ladder in [0, 1]; each rung only counts once the earlier ones hold.

| Component | Weight | Rule |
|---|---|---|
| compile | 0.10 | passes static checks and compiles |
| lint | 0.05 | Verilator `-Wall` clean; decays to 0 at 5 warnings |
| functional | 0.70 | × fraction of hidden tests passed; halved if the design does not synthesize |
| area/depth bonus | 0.15 | only for an accepted design. Matching the reference earns 80%; a reference-to-candidate ratio of 1.25 (20% fewer cells or logic levels) earns 100% (70% area, 30% depth). A missing metric earns nothing |
| test-escape penalty | −0.10 | every test passes but the formal check finds a difference |
| latch penalty | −0.05 | any inferred latch |

The area and depth numbers are Yosys generic-gate proxies, not signoff power,
performance, and area: there is no cell library, placement, routing, or static timing.

Design choices, and the failure modes they guard against:

- **Proxy rewards can be gamed.** A candidate that calls `$finish` would stop the
  simulation before any assertion fails. Static checks reject it with reward 0
  (`popcount16/candidates/hack_finish.sv`). These checks cover specific, known hacks;
  they are not a general defense.
- **Tests are a proxy too.** The formal check catches designs that pass every sampled
  test but are wrong, and the escape penalty makes that worse than an honest failure
  to collect the area bonus.
- **Simulation is not hardware.** Code with `#` delays can pass tests in a simulator.
  Yosys silently drops delays, so the harness uses Verilator's `STMTDLY` warning to mark
  the design as not synthesizable and halves its functional credit
  (`uart_tx/candidates/nonsynth_delays.sv`).
- **Area must not be bought with correctness.** A tiny wrong design (for example the
  fixed-priority arbiter at 7 gates versus 35) earns no area bonus at all.
- **Hidden tests check behavior, not structure.** Testbenches compare against a Python
  model, not the reference RTL, so any correct micro-architecture scores full marks
  (the FSM, shift-register, and extra-MSB-pointer alternatives all pass, formally too).
- **Determinism.** Fixed simulator and stimulus seeds: the same code always gets the
  same reward.

## Tool latency

EDA tools are the slow part of an RL step. The harness keeps it low:

1. **Early exit.** Static checks and compile take milliseconds; a candidate that fails
   them never reaches simulation, synthesis, or formal.
2. **Parallel stages.** Lint, synthesis, simulation, and the formal check run
   concurrently, so a step costs the slowest tool, not the sum.
3. **Content-addressed cache.** Results are keyed on (task files, candidate text, tool
   versions, reward weights, formal on/off). Duplicate samples, common in RL batches,
   cost nothing.
4. **Parallel episodes.** `--workers N` runs episodes concurrently.
5. **Resource limits.** Every tool runs in its own session with a wall-clock timeout
   and CPU, memory, and file-size limits (set by `prlimit`, not `preexec_fn`, which is
   unsafe with threads), and a timeout kills the whole process group. Tools get a
   minimal environment, so API keys and tokens never reach a simulator running
   generated code. Output goes to a capped file, so a design that prints without end
   cannot exhaust memory. A missing tool stops the run with an error instead of being
   scored as a candidate failure. This is not a hardened sandbox: there is no
   container, syscall filter, or network isolation.

Measured on a 2-core Linux machine with an empty cache, one grading step takes 0.8 to
2.1 seconds depending on the task; simulator start-up dominates, except for
`fifo_sync`, where the formal check takes about 1.7 seconds.

## Experiments: running Claude on the tasks

`run` plays full episodes and reports, per arm:

- **accepted on the first attempt** (the acceptance rule above);
- **first attempt passes tests**: hidden tests only, so the gap between the two shows
  how often tests alone would have been fooled;
- **accepted within N turns**;
- **test escapes**: attempts that pass every test but fail the formal check;
- **inconclusive** attempts, reported separately rather than hidden in a rate;
- episodes run and episodes that hit an error (a timeout, an API failure): these count as
  unsolved in every rate, with the scores they reached before the error, and are also
  reported separately. Rates are shown with their denominators (e.g. "2/8");
- mean turns, grading latency (median and 95th percentile), cache hit rate, and token
  usage.

The default experiment compares two arms per model with the same turn budget:
**full** feedback (compiler, test, and formal diagnostics between attempts) against
**none** (the agent only learns the attempt was not accepted and tries again). The
first attempt sees the same prompt in both arms, so the difference in later turns
measures what the tool feedback adds over plain retries. With `--paired` (instead of
`--feedback`), each episode makes one first attempt and branches it into both arms,
which removes first-attempt noise from the comparison. The arms share only that first
attempt: each branch is forked from the state right after it, so neither arm sees the
other's feedback, and each arm's tokens and time cover only its own turns (the shared
first call is reported once, under `shared_first`). The run writes `OUT__full.json`,
`OUT__none.json`, and `OUT__paired.json`, which counts the episodes solved in both
arms, in only one, or in neither, plus the exact McNemar p-value (a two-sided binomial
test on the discordant pairs). Episodes whose first attempt was accepted cannot differ
between the arms, and episodes whose first attempt failed with an error are counted
separately ("errored"), so only the discordant episodes carry information about the
difference.

Every result file records the model, effort, sampling settings, git commit (marked
`-dirty` if the code had uncommitted changes), Python, tool, and cocotb versions, and
the full per-turn trajectory of every episode.

All agents return the model's reply text, and the environment extracts the design with
one shared function: the last code block (or bare `module ... endmodule` text) that
defines the task's top module, plus any helper modules it instantiates that are defined
elsewhere in the reply. Testbenches and prose are left out.

**On GitHub (no local setup):** add the repository secret `ANTHROPIC_API_KEY`
(Settings → Secrets and variables → Actions), then open Actions → eval → Run workflow.
Inputs: models (comma-separated), tasks (`all`, or a comma-separated list for a cheap
smoke run), episodes per task, attempts per episode, paired (on by default), feedback
arms (used only when paired is off), effort, and the number of parallel episodes. The run
prints the most API calls it can make before it starts, then publishes a summary on the
run page: the results table, the inconclusive and errored counts, input and output
tokens per model (for computing the cost), and the paired outcomes with the McNemar
test. The raw JSON is uploaded as the `eval-results` artifact. The API key stays in the
agent process; the grading tools never see it.

**Locally:** the workflow runs [`scripts/ci/eval.sh`](scripts/ci/eval.sh), which takes the
same settings as environment variables:

```bash
pip install -e ".[claude]"
export ANTHROPIC_API_KEY=...
MODELS=claude-sonnet-5-5 TASKS=popcount16,fifo_sync SAMPLES=1 bash scripts/ci/eval.sh
AGENT=replay TASKS=all SAMPLES=1 bash scripts/ci/eval.sh     # offline check, no API calls
```

The agent sends no sampling parameters (Claude Sonnet 5.5 rejects them), streams
responses, and leaves room for thinking in `max_tokens`. `--effort` sets the effort
level; by default each model uses its own. With 8 tasks, 5 episodes per task, and at
most 3 attempts, a paired run makes at most 200 API calls per model (one shared first
attempt, then up to two more in each arm); episodes accepted on the first attempt make
only one. Grading is not the bottleneck: on 2 cores with 8 episodes graded at once, the
slowest formal check took 7 s of its 60 s limit, so 4 parallel episodes on GitHub's
4-core runner leave a wide margin before a design is marked inconclusive.

### Local models (Ollama)

The same experiment runs on free local models served by [Ollama](https://ollama.com),
with no API key. The Ollama agent uses the same system prompt and per-turn messages as
the Claude agent, so the arms are directly comparable.

```bash
ollama list                       # installed models, e.g. qwen3:14b
python -m rtlgym run --agent ollama --model qwen3:14b --paired \
    --samples 1 --max-turns 3 --workers 1 --out results/qwen3-14b.json
python -m rtlgym report results/qwen3-14b__*.json
```

Reasoning that models such as Qwen3 emit (`<think>...</think>` or a separate field) is
removed from the reply and from the conversation history, as the Claude agent returns
only text blocks. The agent sets a 16K-token context window (`--num-ctx`; Ollama's
default would silently truncate multi-turn episodes, and a prompt that fills it is
counted and warned about), caps each reply at 8192 tokens (`--max-tokens`) so a looping
model stops, and waits up to 30 minutes per reply (`--ollama-timeout`). A reply that
times out is not retried, since a retry would regenerate the whole answer; connection
errors and server errors are. `--think on|off` switches reasoning for models that have
it (for other models it is not sent, and the result file says so), and `--seed` sets
the sampling seed (offset per episode, so samples differ). Result files record the
model's digest and quantization, the Ollama version, and the options sent. Use
`--workers 1`: Ollama usually serves one request at a time. `OLLAMA_HOST` or
`--ollama-host` points at a server on another machine.
[`scripts/local/`](scripts/local/) sets this up on a Windows laptop (WSL, the EDA tools,
Ollama) and runs the experiment with one double-click.

### Local model smoke test (preliminary)

A first end-to-end run on a laptop (CPU only, no GPU, 15 GB RAM), to check that the
environment works with real models. **One episode per task, 8 episodes per arm: far
too few for differences between arms or between models to mean anything.** The arms
were run independently (before `--paired` existed), so their first attempts differ.

| Model | Feedback | Solved on 1st try | Solved within 3 turns | Mean best score | Test escapes | Time per reply |
|---|---|---|---|---|---|---|
| llama3.1:8b | full | 1/8 | 2/8 | 0.344 | 0 | 81 s |
| llama3.1:8b | none | 1/8 | 1/8 | 0.241 | 0 | 67 s |
| qwen3:14b, reasoning off | full | 2/8 | 2/8 | 0.484 | 0 | 419 s |
| qwen3:14b, reasoning off | none | 2/8 | 4/8 | 0.567 | 0 | 239 s |

One supportable observation: Llama 3.1 8B's designs failed to compile in most attempts
(14 of 22 attempts in the "none" arm).

Setup: Ollama models `llama3.1:8b` (digest `46e0c10c039e`) and `qwen3:14b` (digest
`bdbd181c33f2`), both Q4_K_M; `num_ctx` 16384, `num_predict` 8192, Ollama's default
sampling; Llama 3.1 has no reasoning mode, and Qwen3 was run with `--think off`
(with reasoning on, one arm did not finish in over 3 hours). Icarus Verilog 12.0,
Verilator 5.020, Yosys 0.33. The code was that of commit 8d2e6ad; the result files
record f30b246 because the Ollama agent was not yet committed when they were made. The
cocotb version was not recorded; the setup installed the newest release (2.1.0), whose
test failure messages are complete (under 2.0.x they were not, a bug fixed since). The
run predates the shared reply extraction, the error accounting, and the other fixes
above; no episode errored.

## Tasks

| Task | Difficulty | Exercises | Formal check |
|---|---|---|---|
| `popcount16` | easy | combinational arithmetic, area/depth trade-off | exhaustive |
| `alu8` | easy | signed vs unsigned, flags, complete case coverage | exhaustive |
| `up_down_counter` | easy | priority of controls, wrap-around, synchronous reset | 12 cycles |
| `edge_detect` | easy | registered vs combinational outputs, cycle timing | 12 cycles |
| `seq_detect_1011` | medium | FSM design, overlapping matches | 12 cycles |
| `fifo_sync` | medium | full/empty logic, pointer wrap, simultaneous read/write | 12 cycles at W=2, DEPTH=4 |
| `rr_arbiter4` | medium | round-robin fairness, pointer update rules | 12 cycles |
| `uart_tx` | hard | cycle-accurate protocol timing, ignoring inputs while busy | 48 cycles |

Each task folder holds `spec.md` (the only thing the agent sees), `ref.sv`, a hidden
`test_<task>.py`, `task.toml` (including the `[formal]` settings), and `candidates/`
with correct alternatives, realistic bugs, a test escape, and adversarial submissions.
`tests/test_tasks.py` checks that every reference and `good_*` candidate passes the tests
and the formal check, every `bug_*` candidate loses at least 0.2 reward and fails the
formal check, the `escape_*` candidate passes every test but is caught by the formal
check, and every `hack_*` or `syntax_*` candidate scores 0. That makes the reward
itself a tested artifact.

Baseline grades (`python -m rtlgym baselines`, excerpt):

```
task             candidate               score  tests  formal  cells  ref  note
alu8             bug_latch.sv            0.650    4/5   error    261  290  latches: formal not supported
alu8             bug_slt_unsigned.sv     0.710    4/5    fail    283  290
alu8             good_case.sv            0.976    5/5    pass    260  290
fifo_sync        bug_full_flag.sv        0.383    2/6    fail    236  236
fifo_sync        good_ptr_msb.sv         0.979    6/6    pass    236  236
popcount16       escape_rare_input.sv    0.750    3/3    fail     78   64  test escape
popcount16       hack_finish.sv          0.000    0/0 skipped      -   64  $finish rejected
rr_arbiter4      bug_fixed_priority.sv   0.430    2/5    fail      7   35
uart_tx          good_shift.sv           0.895    6/6    pass    128   51
uart_tx          nonsynth_delays.sv      0.168    1/6    fail      0   51  delays: not synthesizable
```

### Adding a task

1. Create `tasks/<id>/task.toml` with `top`, `difficulty`, `tags`, a `[formal]` table
   (`depth`, `reset`, optional `params`), and optionally `demo_trajectory` (candidate
   files the replay agent submits in order).
2. Write `spec.md`: the exact interface, the cycle-level behavior, and reset values.
   If two careful engineers could read it differently, the task is measuring the spec,
   not the model.
3. Write `ref.sv` (lint-clean, synthesizable) and `test_<id>.py` with a Python model.
4. Add `candidates/good_*.sv` and `candidates/bug_*.sv`, then run `pytest`.

## Layout

```
rtlgym/
  env.py          multi-turn Gym-style environment and feedback formatting
  evaluator.py    staged, parallel, cached grading pipeline
  formal.py       miter-based equivalence check and counterexample parsing
  reward.py       shaped reward
  tools.py        resource-limited wrappers for iverilog, verilator, yosys, cocotb
  checks.py       static checks and code extraction from LLM replies
  simworker.py    child process that runs one cocotb testbench
  agents/         scripted replay agent (offline), Claude agent (API), Ollama agent (local)
  cli.py          list / score / baselines / run / report
tasks/            8 tasks with specs, references, hidden tests, candidates
tests/            182 tests: reward, formal, tools, extraction, end-to-end grading, environment, agents, CLI
scripts/ci/       eval.sh (the eval workflow's run logic) and its summary helper
scripts/local/    Windows + WSL + Ollama setup and run scripts for local models
.github/workflows ci.yml (lint and tests on every push), eval.yml (manual model runs, via scripts/ci/eval.sh)
```

## Limitations and next steps

- **Small, public benchmark.** Eight textbook-size designs exercise the harness; they
  are not enough to measure how a model generalizes to production RTL. Their tests,
  seeds, and references are public, so treat them as development fixtures: a real
  evaluation needs private, held-out task families and independently seeded checks.
- **Equal-weight tests.** Each cocotb test counts once toward the functional score,
  whatever it covers. Scoring explicit requirement groups would make partial credit
  mean more.
- **Bounded proofs.** Sequential checks cover a fixed number of cycles from reset, with
  reset held low afterwards. k-induction would turn some of them into full proofs.
- **Proxies, not signoff.** Area and depth are generic-gate estimates. A Liberty-based
  flow (Yosys and ABC with a real cell library, then OpenSTA) would give area and
  timing in physical units, and would let the proxies be checked against them.
- **Why cocotb and not UVM.** UVM needs a commercial simulator; cocotb runs on
  open-source simulators, so every check here runs in public CI.
- **Language coverage.** Icarus Verilog supports a subset of SystemVerilog (for example
  it requires explicit casts when assigning a ternary of enum values). A Verilator
  simulation backend would widen coverage and speed up long tests.
- **No policy training yet.** The environment exposes a Gym-style interface and reward;
  connecting it to an RL trainer is future work.

## Author

**Ramin Rajaei**, Ph.D.
[GitHub](https://github.com/iiamramiin) · [Google Scholar](https://scholar.google.com/citations?user=lL4svjsAAAAJ)

## License

MIT. See [LICENSE](LICENSE).
