# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""LLM agent backed by the Claude API (optional; needs ANTHROPIC_API_KEY).

The conversation is kept across turns, so the model sees its own previous
attempt and the tool feedback, the same way an RL rollout would. Assistant turns
are stored exactly as returned (including any thinking blocks) and the
conversation is append-only, as the API expects for multi-turn use.

Current Claude models choose their own sampling settings: the request sends no
temperature. Thinking counts toward max_tokens, so the default limit is high and
responses are streamed.
"""

from __future__ import annotations

import os

from .base import Agent, first_prompt

SYSTEM_PROMPT = """You are an expert RTL design engineer.
Write synthesizable SystemVerilog (IEEE 1800-2012) that implements the given spec exactly.
Rules:
- Return exactly one module with the requested name and port list, in one ```systemverilog code block.
- Use only synthesizable constructs: no delays, no initial blocks for logic, no system tasks.
- Use synthesizable SystemVerilog accepted by Icarus Verilog 12 (-g2012) and Verilator.
- Prefer clean, lint-free code and small area once the design is correct.
When you get tool feedback, fix the reported problems and return the complete corrected module."""

VERIFY_SYSTEM_PROMPT = """You are a design verification engineer.
Use the task's exact module header and port widths. Submit exactly one self-contained
rtl_checker module in one SystemVerilog code block. Every port is an input observing a DUT
signal. Read only these ports and private checker variables. The judge instantiates the DUT.

Use immediate assert(expression); statements without action blocks. Include at least one
assertion. Place assertions in always_comb, always @*, or, for a task with a clock, always
@(posedge clk) or always_ff @(posedge clk). Clocked assertions observe values before the DUT and
checker perform their nonblocking updates, so they see results of the preceding edge.

Private monitor variables may use four-state logic, reg, int, or integer, signed or unsigned,
with packed widths up to 256 bits. Two-state bit declarations are unsupported. One unpacked
array dimension [0:N] is supported for module variables, with at most 64 entries. If the native
parser reduces an array index ambiguously, the checker is rejected. Compute such indices in a
full-width private integer temporary before indexing. Explicit part-selects and recoverable
indices are permitted. Power-of-two constant remainder is supported in array indices.
Parameters and localparams must resolve to defined integer constants. Declare
persistent monitor registers at module scope. Clocked monitor assignments may be blocking or
nonblocking, with ordinary SystemVerilog ordering. Use blocking assignments for combinational
calculations and temporary values. Continuous assignments may compute private checker signals.
Block-scoped scratch variables must be assigned completely before every read in each process
activation. Module variables may retain monitor history. Combinational calculations must not
infer latches. Each variable has at most one procedural or continuous writer, apart from its permitted
initialization.

A private register may have a constant declaration initializer or be initialized by constant
blocking assignments in an initial block. Constant expressions, localparams, and whole-array
declaration assignment patterns are supported. Bounded constant for loops may initialize array
elements. Module-scope monitor storage may start arbitrary: reset and starting values are
optional, including for private arrays and partially initialized words. Formal checks assertions
for every possible initial value of unspecified storage. Guard reads until stored data is known.
Repeated assignments in one initial block execute in order. Overlapping
initializations from separate processes are rejected. Initialization cannot read ports or
contain data-dependent branches, timing controls, or assertions. It sets checker storage only
and does not initialize the DUT.

Supported computations include +, -, *, bitwise and logical operations, comparisons, shifts,
conditional expressions, concatenation, replication, and packed bit/part selection. Remainder
(%) is supported only with a positive constant divisor that is a power of two. Use defined
integer constants without X/Z digits. Use ordinary if/else, case, and constant-bounded for
loops. Each loop has at most 128 iterations, with at most 1024 expanded iterations in total.
Functions must be nonrecursive, use supported integer types, and write only function-local
variables; function-local unpacked arrays are unsupported. Function-local variables must be
completely assigned before every read on every
call. Functions cannot retain history between calls; keep monitor history at module scope.
Local declaration initializers in automatic
functions execute on every call. Static function declaration initializers are unsupported.
Supported system functions are $signed, $unsigned, $clog2, $bits, $countones, $onehot, and
$onehot0. Their arguments must be packed expressions of at most 256 bits. The last three count
only bits exactly equal to 1'b1, including when other bits are X or Z.

Do not drive observed ports, instantiate other modules, reference DUT internals, constrain
inputs with assume or restrict, or use cover, bind, force, release, imports, exports, tasks,
classes, interfaces, or external calls. Do not use preprocessor directives or includes,
concurrent assertions, assertion action blocks, unique/priority case modifiers, casex/casez,
runtime division or power, other remainder operations, delays or waits, event controls beyond
the permitted process event, other clocks, or other system functions/tasks. In particular, $past
and random/file/OS operations are unsupported. Identifiers beginning __rtlgym_ are reserved.

Limits are 64 KiB of submitted source, 64 assertions, 16 functions, and 4096 declared private
bits. Native SystemVerilog parsing has a 15-second limit, with no checker conversion fallback.
Parser output is limited to 4 MiB, 12,000 syntax elements, and 128 nested syntax levels.
Each expanded checker variant is limited to 1 MiB. A task may publish an overall grading
time budget; exhaustion is
inconclusive, earns no reward, and is not cached. Follow the task's initialization, reset,
timing, and parameter profile. When you receive feedback, return the complete corrected checker."""

DEFAULT_MODEL = "claude-sonnet-5-5"


def system_prompt_for_task(obs: dict) -> str:
    return VERIFY_SYSTEM_PROMPT if obs.get("task_kind") == "verify" else SYSTEM_PROMPT


class ClaudeAgent(Agent):
    def __init__(self, model: str | None = None, max_tokens: int = 32000,
                 effort: str | None = None, client=None, max_retries: int = 5):
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("pip install anthropic to use the Claude agent") from exc
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError("set ANTHROPIC_API_KEY to use the Claude agent")
            # The SDK retries rate limits, overloads, and connection errors itself.
            client = anthropic.Anthropic(max_retries=max_retries)
        self.client = client
        self.model = model or os.environ.get("RTLGYM_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens
        self.effort = effort
        self.messages: list[dict] = []
        self.system_prompt = SYSTEM_PROMPT
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                      "refusals": 0, "truncated": 0}

    def begin_episode(self, obs: dict) -> None:
        self.messages = []
        self.system_prompt = system_prompt_for_task(obs)

    def act(self, obs: dict) -> str:
        if not self.messages:
            self.system_prompt = system_prompt_for_task(obs)
            content = first_prompt(obs)
        elif obs["feedback"]:
            content = ("Tool feedback on your last submission:\n\n```\n" + obs["feedback"]
                       + f"\n```\n\nYou have {obs['turns_left']} attempt(s) left. "
                       "Return the full corrected module.")
        else:
            # Retry without diagnostics (feedback="none"): the control arm for measuring
            # what tool feedback adds over simply trying again.
            content = (f"Your last submission was not accepted. You have {obs['turns_left']} "
                       "attempt(s) left. Return the full module.")
        self.messages.append({"role": "user", "content": content})
        msg = self._call()
        # Keep the full assistant turn (thinking blocks included) for the next request.
        self.messages.append({"role": "assistant", "content": msg.content})
        return "".join(getattr(b, "text", "") for b in msg.content
                       if getattr(b, "type", "") == "text")

    def _call(self):
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": self.system_prompt,
            "messages": list(self.messages),
        }
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        with self.client.messages.stream(**kwargs) as stream:
            msg = stream.get_final_message()
        self.usage["calls"] += 1
        u = getattr(msg, "usage", None)
        if u is not None:
            self.usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
            self.usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0
        stop = getattr(msg, "stop_reason", None)
        if stop == "refusal":
            self.usage["refusals"] += 1
        elif stop == "max_tokens":
            self.usage["truncated"] += 1
        return msg
