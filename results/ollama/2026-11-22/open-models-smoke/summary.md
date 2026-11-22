# Local open-model probes and smoke tests, November 22

Only probes and the two-task paired smoke were run. Overnight experiments have
not started. The completed 8K runs used generation commit `8d4818d`, one worker,
`num_ctx=8192`, `num_predict=8192`, `think=false`, base seed `20261122`, and a
1,800-second reply timeout. The smoke has one sample on each task and three turns.

The PC reports 15.43 GiB usable RAM, an Intel Core Ultra 7 155U (12 cores,
14 logical processors), and Intel Graphics. Both models ran on the CPU:
Ollama reported zero VRAM use. The integrated adapter's reported memory is not
dedicated model VRAM. Ollama was 0.40.16; both installed models are Q4_K_M.

| Model | Provider | Stored weights (GiB) | 75% RAM rule |
|---|---|---:|---|
| llama3.1:8b | Meta | 4.58 | Eligible |
| qwen3:14b | Qwen / Alibaba | 8.64 | Eligible |
| qwen3:30b-a3b | Qwen / Alibaba | 17.28 | Skipped |

The rule's ceiling is 11.58 GiB. The 30B model exceeds even total usable RAM;
its smaller active-parameter count does not make its full weights fit this rule.
The rule checks weights only, not runtime storage or the rest of the PC.

## Measurements

| Model | 8K probe seconds/reply | Probe accepted | Design smoke seconds/reply | Whole smoke seconds/reply | Unique smoke calls |
|---|---:|---:|---:|---:|---:|
| llama3.1:8b | 78.13 | 0/1 | 113.05 | 115.38 | 6 |
| qwen3:14b | 770.40 | 1/1 | 685.91 | 311.42 | 6 |

Reply time uses Ollama's `total_duration`, including loading and inference.
The probe is one completed reply, so it is a small timing sample. The mixed
smoke also contains verification replies and is not a design-only speed estimate.

| Model | Accepted first | Within 3, full | Within 3, none | 95% CI, each rate/arm | Informative pairs | Discordant | Exact McNemar p |
|---|---:|---:|---:|---|---:|---:|---:|
| llama3.1:8b | 1/2 | 1/2 | 1/2 | [1.26%, 98.74%] | 1 | 0 | 1 |
| qwen3:14b | 1/2 | 1/2 | 1/2 | [1.26%, 98.74%] | 1 | 0 | 1 |

The intervals are two-sided 95% Clopper-Pearson bounds. Shared first attempts
are counted once for calls and paired episodes. Both arms retain all episodes
in their pass-rate denominators. With two episodes and zero discordances per
model, this smoke does not estimate a feedback benefit or establish its absence.

- Llama's design failed in both arms with real compile errors, including multiple
  continuous drivers. Its checker passed the correct-design gate and caught 11/11 mutants.
- Qwen's design passed simulation and exhaustive equivalence on the first try.
  Its checker put an immediate assertion outside a procedural block, which is
  invalid syntax. Removing the action block did not repair that placement.
  Mutant coverage and false alarms were unassessed for those rejected checkers.
- There were no API errors, output-limit cutoffs, resource-inconclusive grades,
  test escapes, or context-limit warnings in the completed 8K smoke. A missing
  context warning is not proof that no history was truncated internally.

The probe and smoke can produce different submissions with the same recorded
seed. Preserve the raw files, model digest, options and server version; a fixed
seed does not guarantee bit-identical replies.

## The initial 16K setup check

The initial Llama probe at main `0833074` completed three replies averaging
88.99 seconds and did not solve popcount. Its failures were arithmetic errors,
confirmed by simulation and formal counterexamples. The initial Qwen probe was
stopped without a completed episode JSON after memory pressure: about 92 MiB
free physical RAM and recent generation near 0.2 tokens/second. It is a setup
diagnostic, not a scored model failure or an output-limit truncation.

At 16K context Ollama reported Qwen's runtime size as 11.46 GiB. At 8K it
reported 10.20 GiB; Llama's runtime size fell from 6.85 to 5.83 GiB.
The local wrapper now defaults to 8K, while the CLI/agent defaults remain unchanged.
Larger contexts need more memory, as the [Ollama context guide](https://docs.ollama.com/context-length)
also explains. The installed Qwen metadata supports both Boolean thinking values;
its default is true, and these runs explicitly sent false. See
[Ollama thinking controls](https://docs.ollama.com/capabilities/thinking).

## Reproducibility and implementation checks

Each arm JSON's `summary`, and each paired JSON's `meta`, records Ollama version,
full model digest, quantization, `num_ctx`, `num_predict`, requested/effective
thinking setting, seed base and offset rule, Python and generation commit.
Their `tools` dictionaries record cocotb 2.1.0, Icarus 12.0, Verilator 5.020,
Yosys 0.33 and sv2v v0.0.13. Full version strings remain in the raw files.
Sampling options not listed were not overridden; model and server defaults apply.

The follow-up paired fix grades the first submission once for every task kind;
previously caching masked duplicate design/verification grading. It also reports
shared grading exceptions as errors. The four saved smoke first grades, sources
and tool reports match between arms, so that fix does not change these outcomes.
The [offline audit](shared-grade-audit.json) records the check. Candidate grading,
the environment API, grader versions and system-prompt bytes were not changed.

Runner checks cover explicit task selection, paired usage/truncation, the verify
prompt, metadata in all three result files, the named-model RAM guard, Windows
settings/output-path transport, and copying tracked archive fixtures while keeping
local outputs. Exact intervals and per-model paired tests also have regression tests.
The offline block combiner validates frozen generation metadata and contiguous seeds,
then recomputes counts and statistics without model calls.

Raw JSON and the original smoke summary are copied byte for byte. Hashes are in
`manifest.json`; runtime snapshots and hardware/configuration records are separate.
Completed overnight cohorts will go under `results/ollama/YYYY-MM-DD/paper1-MODEL/`,
with raw parts and derived combined reports kept distinct. See [the proposed run plan](run-plan.md).
