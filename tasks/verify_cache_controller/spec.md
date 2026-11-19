# Verify a cache transaction contract

A checker earns the average fraction of incorrect behaviors caught in each mutation family.
It must accept every correct implementation, including the allowed timing and inactive-data
freedom below. False alarms, source rejection and unresolved proofs earn zero.

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
timing, and parameter profile. When you receive feedback, return the complete corrected checker.

```systemverilog
module rtl_checker #(
    parameter integer DATA_W = 2,
    parameter integer TAG_W = 1,
    parameter integer INDEX_W = 1
) (
    input logic clk, rst, inv_valid, inv_ready,
    input logic cpu_req_valid, cpu_req_ready,
    input logic [TAG_W+INDEX_W:0] cpu_req_addr,
    input logic cpu_rsp_valid, cpu_rsp_ready,
    input logic [DATA_W-1:0] cpu_rsp_data,
    input logic mem_req_valid, mem_req_ready,
    input logic [TAG_W+INDEX_W-1:0] mem_req_addr,
    input logic mem_rsp_valid, mem_rsp_ready,
    input logic [2*DATA_W-1:0] mem_rsp_data
);
    // Add assertions and private monitor state.
endmodule
```

## Concrete profile and transfers

This profile fixes DATA_W=2, TAG_W=1 and INDEX_W=1: two direct-mapped lines,
two 2-bit words per line, two tags per index. CPU word addresses have the
word offset at bit 0, line index at bit 1, and tag at bit 2. Memory line
addresses omit bit 0. A refill's low two bits are word 0; its high two bits
are word 1. A rising edge transfers a channel when valid and ready are high
and rst is low. Inputs matter only on transfer edges. Inputs may otherwise
change arbitrarily; no environment fairness is assumed.

## Blocking transactions and latency freedom

There is at most one CPU read outstanding. When idle, inv_ready is high and
cpu_req_ready equals inv_ready && !inv_valid. A transferred invalidation
clears all cached valid bits and has no response. It has priority over a
CPU read. Busy implementations accept neither a new read nor invalidation,
including on the edge that transfers the prior CPU response.

On an accepted CPU read, classify hit or miss using the pre-edge cache.
A hit requires a valid index and a matching complete tag. A hit returns
the selected cached word, with no memory request. A miss issues exactly
one memory request for the accepted CPU address with the word-offset bit
removed. Hold mem_req_valid and its address until that request transfers.

mem_rsp_ready is low before the memory request transfers, high immediately
after that transfer, and remains high until one refill transfers. Early or
unsolicited memory response inputs are ignored. A transferred refill replaces
the requested index's valid bit, tag and complete two-word line. Return the
requested word from that refill to the CPU. Hold cpu_rsp_valid and its data
until the CPU response transfers. No other memory request, refill acceptance
or CPU response is permitted while the associated transaction is absent.

Timing is deliberately flexible. After a CPU miss is accepted, the first
mem_req_valid may appear immediately after that edge or after one or two
additional rising edges. After a hit is accepted, or a refill transfers,
cpu_rsp_valid has the same allowance of zero, one or two additional rising
edges. Once asserted, valid cannot be withdrawn before its transfer. The
implementation may return to idle immediately after a CPU response transfer,
or spend one additional rising edge rearming before asserting inv_ready.
The implementation starts idle immediately after the reset edge. These are
local output deadlines; stalls caused by mem_req_ready, mem_rsp_valid or
cpu_rsp_ready have no deadline and do not consume the pre-offer allowance.

Data is meaningful only while its valid output is high. Inactive
cpu_rsp_data and mem_req_addr may be zero, retained, or any other value.
A checker that insists on one implementation's exact latency or inactive
payload values is incorrect.

## Reset and bounded checking

rst is active high and synchronous for stored state. All ready and valid
outputs must be low whenever rst is high. A reset edge empties the cache,
abandons the pending transaction and establishes idle. Tags and data in
invalid entries do not matter. The environment discards in-flight work on
reset, so an abandoned CPU read must be requested again and miss.

The formal profile unrolls 12 transitions plus one final observation. Reset
is high on the first transition and low thereafter. DUT and checker storage
without explicit initialization are arbitrary before reset. A rising-edge
immediate assertion sees values before that edge's nonblocking updates,
including the outputs produced by the previous edge. Sample handshakes and
cache changes with that ordering. Gate assertions that require established
state until reset has established it. The grading tool calls share a
60-second budget; a proof or overall budget exhaustion is
inconclusive and earns no reward. No full cache RTL is supplied.
