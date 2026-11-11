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
| PPA proxy | Yosys | generic-gate count (area), logic depth (delay), flops, inferred latches |

The environment is multi-turn: after each attempt the agent sees compiler errors, lint
warnings, the names and messages of failing hidden tests, and its synthesis numbers next
to the reference design, and can try again.

```
spec.md ──► agent ──► RTL ──► static ─► compile ─┬─► lint  ──┐
   ▲                                             ├─► synth ──┼─► reward + feedback
   └──────────────── feedback ◄──────────────────┴─► tests ──┘
```

## Quick start

```bash
sudo apt-get install -y iverilog verilator yosys        # Ubuntu 24.04
pip install -e ".[dev]"

python -m rtlgym list                                   # 8 tasks
python -m rtlgym score fifo_sync my_fifo.sv             # grade one file
python -m rtlgym baselines                              # grade every hand-written candidate
python -m rtlgym run --agent replay                     # multi-turn episodes, no API key needed
pytest -q                                               # 64 tests
```

With a Claude API key:

```bash
pip install -e ".[claude]"
export ANTHROPIC_API_KEY=...
python -m rtlgym run --agent claude --model claude-sonnet-5-5 --samples 5 --max-turns 3 --out results.json
```

`run` reports pass@1 (first attempt passes every hidden test), solve rate within the
turn budget, mean first and best score, and token usage.

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
  (per-stage pass/fail, logs, gate counts, timings).
- `reward_mode="improvement"` pays only the gain over the best score so far, so the
  episode return equals the best score reached and re-submitting the same answer earns
  nothing. `reward_mode="score"` pays the raw score every turn.
- `feedback` is `"none"` (single-shot eval), `"summary"` (counts only), or `"full"`.
  Full feedback reveals failing test names and messages, which is useful for training
  a debugging loop but leaks some test information; use `summary` or `none` for evals.

## Reward

The reward is a ladder in [0, 1]; each rung only counts once the earlier ones hold.

| Component | Weight | Rule |
|---|---|---|
| compile | 0.10 | passes static checks and compiles |
| lint | 0.05 | Verilator `-Wall` clean; decays to 0 at 5 warnings |
| functional | 0.70 | × fraction of hidden tests passed; halved if the design does not synthesize |
| PPA | 0.15 | only when every test passes, synthesis succeeds, and no latches are inferred. Matching the reference earns 80%; beating it by 25% earns 100% (70% area, 30% depth) |
| latch penalty | −0.05 | any inferred latch |

Design choices, and the failure modes they guard against:

- **Proxy rewards can be gamed.** A candidate that calls `$finish` would stop the
  simulation before any assertion fails. Static checks reject it with reward 0
  (`popcount16/candidates/hack_finish.sv`).
- **Simulation is not hardware.** Code with `#` delays can pass tests in a simulator.
  Yosys silently drops delays, so the harness uses Verilator's `STMTDLY` warning to mark
  the design as not synthesizable and halves its functional credit
  (`uart_tx/candidates/nonsynth_delays.sv`).
- **PPA must not be bought with correctness.** A tiny wrong design (for example the
  fixed-priority arbiter at 7 gates versus 35) earns no PPA bonus at all.
- **Hidden tests check behavior, not structure.** Testbenches compare against a Python
  model, not the reference RTL, so any correct micro-architecture scores full marks
  (the FSM, shift-register, and extra-MSB-pointer alternatives all pass).
- **Determinism.** Fixed simulator and stimulus seeds: the same code always gets the
  same reward.

## Tool latency

EDA tools are the slow part of an RL step. The harness keeps it low:

1. **Early exit.** Static checks and compile take milliseconds; a candidate that fails
   them never reaches simulation or synthesis.
2. **Parallel stages.** Lint, synthesis, and simulation run concurrently, so a step
   costs the slowest tool, not the sum.
3. **Content-addressed cache.** Results are keyed on (task files, candidate text, tool
   versions, reward weights). Duplicate samples, common in RL batches, cost nothing.
4. **Parallel episodes.** `--workers N` runs episodes concurrently.
5. **Sandboxing.** Every tool runs in a subprocess with a wall-clock timeout and CPU and
   memory limits, so an infinite loop in generated RTL cannot stall a training run.

On a laptop, grading all 32 hand-written candidates takes about 12 seconds; one step
takes 1 to 2 seconds, dominated by simulator start-up.

## Tasks

| Task | Difficulty | Exercises |
|---|---|---|
| `popcount16` | easy | combinational arithmetic, area/depth trade-off |
| `alu8` | easy | signed vs unsigned, flags, complete case coverage |
| `up_down_counter` | easy | priority of controls, wrap-around, synchronous reset |
| `edge_detect` | easy | registered vs combinational outputs, cycle timing |
| `seq_detect_1011` | medium | FSM design, overlapping matches |
| `fifo_sync` | medium | full/empty logic, pointer wrap, simultaneous read/write |
| `rr_arbiter4` | medium | round-robin fairness, pointer update rules |
| `uart_tx` | hard | cycle-accurate protocol timing, ignoring inputs while busy |

Each task folder holds `spec.md` (the only thing the agent sees), `ref.sv`, a hidden
`test_<task>.py`, and `candidates/` with correct alternatives, realistic bugs, and
adversarial submissions. `tests/test_tasks.py` checks that every reference passes, every
`good_*` candidate passes, every `bug_*` candidate loses at least 0.2 reward, and every
`hack_*` or `syntax_*` candidate scores 0. That makes the reward itself a tested artifact.

Baseline grades (`python -m rtlgym baselines`):

```
task               candidate                       score  tests  cells   ref
alu8               ref.sv                          0.970    5/5    290   290
alu8               bug_latch.sv                    0.650    4/5    261   290
alu8               bug_slt_unsigned.sv             0.710    4/5    283   290
alu8               good_case.sv                    0.976    5/5    260   290
fifo_sync          bug_full_flag.sv                0.383    2/6    236   236
fifo_sync          bug_fwft.sv                     0.267    1/6    188   236
fifo_sync          good_ptr_msb.sv                 0.979    6/6    236   236
popcount16         hack_finish.sv                  0.000    0/0      -    64   ($finish rejected)
popcount16         syntax_error.sv                 0.000    0/0      -    64
rr_arbiter4        bug_fixed_priority.sv           0.430    2/5      7    35
uart_tx            bug_short_stop.sv               0.267    1/6    131    51
uart_tx            good_shift.sv                   0.895    6/6    128    51
uart_tx            nonsynth_delays.sv              0.168    1/6      0    51   (delays: not synthesizable)
...
```

### Adding a task

1. Create `tasks/<id>/task.toml` with `top`, `difficulty`, `tags`, and optionally
   `demo_trajectory` (candidate files the replay agent submits in order).
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
  reward.py       shaped reward
  tools.py        sandboxed wrappers for iverilog, verilator, yosys, cocotb
  checks.py       static checks and code extraction from LLM replies
  simworker.py    child process that runs one cocotb testbench
  agents/         replay agent (offline) and Claude agent (API)
  cli.py          list / score / baselines / run
tasks/            8 tasks with specs, references, hidden tests, candidates
tests/            64 tests: reward unit tests, end-to-end grading, env, agent
```

## Limitations and next steps

- Icarus Verilog supports a subset of SystemVerilog (for example it requires explicit
  casts when assigning a ternary of enum values). A Verilator simulation backend would
  widen language coverage and speed up long tests.
- Generic-gate counts are a proxy. A Liberty-based flow (Yosys + ABC with a real cell
  library, then OpenSTA) would give area and timing in physical units.
- Next tasks: formal properties with SymbiYosys as a second, stronger verifier;
  spec-to-assertion generation; debug tasks (given a failing design and a log, fix it);
  and larger designs that split into multiple modules.

## License

MIT
