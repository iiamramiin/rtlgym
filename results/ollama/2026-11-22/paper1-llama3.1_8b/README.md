# Llama 3.1 8B paired design run

The November 22, 2026 run used `llama3.1:8b`, Q4_K_M (digest `46e0c10c039e`),
with Ollama 0.40.16 on CPU. The context window and output-token limit were both 8,192
(`num_ctx=8192`, `num_predict=8192`). The base seed was 20261122 plus the zero-based episode index. The 12
original design tasks ran three times each. Full feedback and plain retries
shared the first submission and had at most three turns each.

The generation and grading commit was `a234a86`. The run recorded Icarus Verilog
12.0, Verilator 5.020, Yosys 0.33 (2584903a060), pinned sv2v v0.0.13, and cocotb
2.1.0. [Run summary](summary.md)

| Outcome | Full feedback | Plain retries |
| --- | ---: | ---: |
| Accepted on first try | 4/36 | 4/36 |
| Accepted within three turns | 6/36 | 7/36 |
| Retry turns that raised the score | 13/62 | 17/62 |

There was one discordant pair, in favor of plain retries. The exact paired
McNemar p-value was 1. No reply reached the output limit. The largest recorded
prompt plus reply used 7,772 of 8,192 tokens. Of 62 feedback messages leading to
another turn, 49 were clear in the run audit. They comprised 33 named test
mismatches and 16 compiler errors.

## Tool audit

- Of 47 unique compile failures, 31 were also rejected by Verilator 5.020.
  Verilator accepted three with warnings, although the RTL was illegal under
  IEEE 1800. The other 13 replies lacked `endmodule`. Their closed Markdown
  fences caused the compiler to report misleading errors on the surrounding
  reply text.
- Four sources used `break`. Yosys 0.33 and 0.71 rejected the construct.
  The sources synthesized after sv2v conversion, and all four failed functional
  tests.
- Icarus 12's `vvp` crashed with an assertion on `sig` on writes to a bounded
  queue in two attempts. The design also failed under Verilator.

Acceptance is unchanged under grader 10. The four `break` sources, recorded in
five attempt rows, gain partial credit because synthesis now succeeds.

| Arm | Task | Episode | Turn | Grader 9 | Grader 10 |
| --- | --- | ---: | ---: | ---: | ---: |
| Full | `alu8` | 28 | 1 | 0.20 | 0.27 |
| Full | `alu8` | 28 | 3 | 0.29 | 0.43 |
| None | `rr_arbiter4` | 11 | 3 | 0.19 | 0.26 |
| None | `alu8` | 28 | 1 | 0.20 | 0.27 |
| None | `alu8` | 28 | 2 | 0.26 | 0.35 |

The last attempt now has three detected latches and incurs the 0.05 latch
penalty. Mean best score stays at 0.288 for full feedback and rises from 0.297
to 0.299 for plain retries. The recorded files retain the grader 9 values.

This cohort covers one 4-bit quantized model, 36 episodes, and CPU-only
execution. The results describe this run.

## Files

The arm JSON files are byte-identical to the recorded files, including the
temporary directories in diagnostics and the exact feedback shown to the model.
The paired JSON and summary are also preserved as recorded. The run log was
omitted because it contained a machine-specific path.
The manifest records byte counts and SHA-256 hashes for the archived payloads.
