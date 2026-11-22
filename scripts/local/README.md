# Local-model runs on Windows (WSL + Ollama)

Ollama serves the installed models on Windows; rtlgym and the EDA tools run in
Ubuntu 24.04 under WSL. One model and one episode run at a time.

| File | Purpose |
|---|---|
| RUN_ME.bat, run_all.ps1 | Check setup, start Ollama if needed, then run the selected mode |
| setup_system.sh | Install Linux tools as root |
| setup_user.sh | Sync code and tracked archive fixtures, create the environment and run tests as a normal user |
| run_eval.sh | Probe, smoke test or explicitly selected full run |
| make_table.py | Local summaries, exact pass-rate intervals, paired tests and timing estimates |

## Start with a probe

The one-click launcher now defaults to **probe**, not a long run. Installed
systems can call the Linux runner directly without changing setup or networking:

    MODELS="llama3.1:8b qwen3:14b qwen3:30b-a3b" THINK=off SEED=20261122 \
        bash scripts/local/run_eval.sh probe

Probe mode runs popcount16, one sample per fitting model, up to three turns
with full feedback. PROBE_TASKS and PROBE_TURNS can change that small probe.
Each model has a separate JSON file in OUT/probe/. Reported seconds per reply
include Ollama's loading and generation time. A small design is a timing sample,
not an upper bound for longer designs or later-turn contexts.

Models whose stored weights exceed 75% of physical RAM are skipped, including
models named explicitly in MODELS. RAM_GB can supply physical RAM in GiB
when it cannot be detected from Windows. The guard excludes obviously oversized
models; KV cache, runtime workspace, Windows and WSL also need memory.

The local runner defaults to an 8K context. A 16K context with Qwen3:14b on the
measured 15.4 GiB machine left almost no free RAM and slowed generation sharply.
Probe memory and reply speed before increasing NUM_CTX. The CLI and agent
context defaults are unchanged.

## Small paired smoke test

    MODELS="llama3.1:8b qwen3:14b" THINK=off SEED=20261122 \
        OUT="$PWD/results/local/smoke" bash scripts/local/run_eval.sh smoke

Smoke mode fixes one sample per model on popcount16 and verify_popcount16,
paired full/none feedback, with the configured TURNS (default three).
SMOKE_TASKS can replace the two task IDs. The model's first attempt is shared;
only unsuccessful episodes continue into the two arms. This default checks both
the design prompt and the verification-specific prompt.

## Explicit overnight runs

Use a new output directory for every set of settings. The mode all runs TASKS,
which may be a comma-separated list or the groups design, repair, verify, or
all. The group all currently includes every task kind. Never use it to mean
the original twelve design tasks.

    TASKS="popcount16,alu8,up_down_counter,edge_detect,seq_detect_1011,fifo_sync,rr_arbiter4,uart_tx,noc_router5,axil_regs,mul_pipe3,crc32_stream"
    MODELS="llama3.1:8b" THINK=off SEED=20261122 TASKS="$TASKS" SAMPLES=5 TURNS=3 \
        PAIRED=1 OUT="$PWD/results/local/paper1-llama" \
        bash scripts/local/run_eval.sh all

That example is a command template, not an overnight sample recommendation.
Choose samples from measured probe and smoke timings, allowing for longer
replies, larger feedback contexts and grading. For twelve unique tasks and
S samples there are 12S paired episodes and at most 60S unique calls with
three turns. noc_router5 is already one of those twelve tasks.

On Windows the same settings are environment variables before RUN_ME.bat:
set RUN_MODE to probe, smoke or explicitly all. Settings survive the
administrator relaunch, including TASKS, NUM_CTX and OUT.

| Setting | Default |
|---|---|
| MODELS | Installed models that pass the RAM guard; space- or comma-separated names |
| TASKS | all, only used for full runs and probe run-time estimates |
| SAMPLES, TURNS, PAIRED | 1, 3, 1 |
| THINK | default; use off for Qwen3 comparisons without reasoning |
| NUM_CTX, MAX_TOKENS | 8192, 8192 |
| TIMEOUT | 3600 seconds per model reply |
| SEED | 0; each episode receives base seed plus episode index |
| OUT | results/local/, ignored by Git |
| OLLAMA_URL | Detect localhost or the Windows host address |

Complete three-file paired result sets are skipped on restart. Partial sets
are rerun. Settings are not compared when skipping; use a fresh OUT when
changing models, tasks, seeds, limits or code. Keep the laptop plugged in with
the lid open; closing the lid can still suspend it.

## Results and reproducibility

Each arm JSON's summary and the paired JSON's meta record:

- ollama.build: Ollama version, full model digest and quantization.
- ollama.options: num_ctx, num_predict and the base seed.
- ollama.think_requested and ollama.think: requested and actual reasoning
  setting, including unsupported settings on non-reasoning models.
- seed: base and per-episode offset rule.
- tools: cocotb, Icarus Verilog, Verilator, Yosys and sv2v versions.
- Commit, Python version, task list, turn budget and feedback arm.

A fixed seed aids reproduction but does not promise identical output across
different model builds, hardware or Ollama versions. Results keep per-turn
output-limit status: an unfinished reply is reported as truncated, while the
original grade and zero reward remain unchanged.

Summaries show exact 95% Clopper–Pearson intervals for each arm's first-attempt
and within-budget pass rates. Errors remain in the denominator. They also show
the exact McNemar test separately for each model's discordant full/none pairs.
Shared first attempts are counted once for total calls. These small,
heterogeneous task sets do not establish performance on unseen task families.

Keep unfinished runs under ignored results/local/. Once a run is complete,
review it and copy its two arm JSON files, paired JSON, summary, probe and
hardware/configuration notes into results/ollama/YYYY-MM-DD/paper1-MODEL/.
Preserve the original JSON bytes and hashes. Probes and smoke tests belong in
their own folders and are not overnight benchmark results.

## Paired grading and multi-night cohorts

The shared first submission is graded once for every task kind and the same
result is applied to both arms, including unresolved tool results. Its elapsed
grading time is stored under shared_first.grade_s. A shared grading exception
marks the pair as errored. Candidate scoring and system prompts are unchanged.

For disjoint task blocks, merge only after the whole cohort finishes:

    python scripts/local/merge_runs.py --model qwen3:14b --out NEWDIR BLOCK_A BLOCK_B

Keep the clean generation commit, models, tool versions and settings fixed.
Advance the second block's base seed by the first block's episode count. The
helper validates those conditions and paired first-attempt integrity, preserves
raw files, and recomputes one model's counts, intervals and McNemar test. It
rejects overlaps, repeated tasks, mixed settings and existing output directories.
Wall time sums the two recorded runs and excludes the gap between nights.

The November 22 probe/smoke archive includes measured timings and ready overnight
commands. It proposes the twelve original designs once (router included), with
Qwen split across two six-task nights to respect this PC's runtime budget.
