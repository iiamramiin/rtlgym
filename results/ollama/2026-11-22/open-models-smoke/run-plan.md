# Proposed Paper 1 overnight runs

These commands have not been run. The original twelve tasks already include
noc_router5. Each primary task appears once in the task list; samples repeat it
as declared. Models run separately, one night at a time, with paired full/none
feedback and three turns. Use 8K context on this PC.

Forecasts use the larger of the completed probe time and design-only smoke time,
add 35% for longer generation/contexts, then add the larger of 12 seconds or the
measured probe wall-time overhead per call. These are planning allowances, not
latency bounds. The ceiling is five unique calls per paired episode; accepted
first attempts use one, so actual runs can finish earlier.

| Run | Samples/task | Tasks | Paired episodes | Unique call range | Budgeted time at call ceiling |
|---|---:|---:|---:|---:|---:|
| llama3.1:8b | 3 | 12 | 36 | 36–180 | about 8.2 h |
| qwen3:14b (each of two nights) | 1 | 6 | 6 | 6–30 | about 9.1 h |

Llama has 36 episodes and at most 180 calls in one night. Four samples/task would
budget about 11 hours with these allowances, so three is the largest balanced
count under ten hours. Qwen has 12 episodes and at most 60 calls across two nights.
One complete Qwen sample already takes 13.64 hours at the probe's maximum-call
wall-time estimate, before allowance. A defensible full twelve-task, single-night
Qwen plan cannot be promised on this PC. The six-task blocks budget about nine
hours each. Their public reference/spec sizes are roughly balanced; actual
reply lengths are unmeasured outside the smoke and can still overrun.

Keep the generation commit, model digest, Ollama/tool versions and other settings
fixed across both Qwen blocks. Do not commit code or archive changes between
them. Leave their outputs under ignored results/local until both finish. Block B's
base seed is A's base plus its six episodes, preserving the global seed sequence.
The merge tool rejects different settings, dirty/unknown commits, overlaps,
missing files and non-contiguous seeds.

From the repository root, in a new PowerShell session before each night, set:

```powershell
$repoPath = (Get-Location).Path
$env:RUN_MODE = "all"
$env:THINK = "off"
$env:NUM_CTX = "8192"
$env:MAX_TOKENS = "8192"
$env:TURNS = "3"
$env:PAIRED = "1"
$env:TIMEOUT = "1800"
$env:RAM_GB = "15.435"
$blockA = "axil_regs,fifo_sync,mul_pipe3,rr_arbiter4,popcount16,up_down_counter"
$blockB = "noc_router5,uart_tx,crc32_stream,alu8,seq_detect_1011,edge_detect"
```

Run just one of the following blocks per night. The existing Windows launcher
keeps the PC awake while open; leave it plugged in with the lid open.

Llama night:

```powershell
$env:MODELS = "llama3.1:8b"
$env:SAMPLES = "3"
$env:TASKS = "$blockA,$blockB"
$env:SEED = "20261122"
$env:OUT = Join-Path $repoPath "results/local/paper1-llama3.1_8b"
& (Join-Path $repoPath "scripts/local/RUN_ME.bat")
```

Qwen night A:

```powershell
$env:MODELS = "qwen3:14b"
$env:SAMPLES = "1"
$env:TASKS = $blockA
$env:SEED = "20261122"
$env:OUT = Join-Path $repoPath "results/local/paper1-qwen3_14b-a"
& (Join-Path $repoPath "scripts/local/RUN_ME.bat")
```

Qwen night B:

```powershell
$env:MODELS = "qwen3:14b"
$env:SAMPLES = "1"
$env:TASKS = $blockB
$env:SEED = "20261128"
$env:OUT = Join-Path $repoPath "results/local/paper1-qwen3_14b-b"
& (Join-Path $repoPath "scripts/local/RUN_ME.bat")
```

Use fresh OUT folders for new configurations. Completed sets are skipped without
comparing settings. All models use one worker. The 30B model remains excluded
by the weights/RAM guard.

## Merge and archive after completion

After both Qwen blocks, map the repository/output paths into WSL and merge offline:

```powershell
$linuxRepo = (wsl -d Ubuntu-24.04 -u rtlgym -- wslpath -a $repoPath).Trim()
$python = "/home/rtlgym/venv-rtlgym/bin/python"
wsl -d Ubuntu-24.04 -u rtlgym -- $python "$linuxRepo/scripts/local/merge_runs.py" `
  --model qwen3:14b --out "$linuxRepo/results/local/paper1-qwen3_14b-combined" `
  "$linuxRepo/results/local/paper1-qwen3_14b-a" "$linuxRepo/results/local/paper1-qwen3_14b-b"
```

Run the local table helper on the combined folder for the per-model interval and
McNemar result. It recomputes the statistics from episodes, not from averaged
p-values. The derived JSON records part hashes and summed running time, excluding
the gap between nights. Original files remain unchanged.

Archive the completed cohorts under:

- results/ollama/YYYY-MM-DD/paper1-llama3.1_8b/: three raw JSONs, summary, probe,
  hardware/configuration and hashes.
- results/ollama/YYYY-MM-DD/paper1-qwen3_14b/: block-a/ and block-b/ raw JSONs,
  combined/ derived JSONs and summary, probe, hardware/configuration and hashes.

Review API errors, resource failures, output/context-limit warnings and raw
trajectories before drawing conclusions. The small public task set and the
two-task smoke do not measure generalization to new chip-design problems.
