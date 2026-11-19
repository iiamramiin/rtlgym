# Verify a synchronous FIFO

A checker earns the average fraction of incorrect behaviors caught in each mutation family. It
must accept every correct implementation. A false alarm, source rejection, or inconclusive proof
earns zero.

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
indices are permitted. Parameters and localparams must resolve to defined integer constants. Declare
persistent monitor registers at module scope. Clocked monitor assignments may be blocking or
nonblocking, with ordinary SystemVerilog ordering. Use blocking assignments for combinational
calculations and temporary values. Continuous assignments may compute private checker signals.
Scratch variables at block or module scope must be assigned completely before every read in each
process activation. Each variable has one procedural or continuous writer, apart from its
permitted initialization.

A private register may have a constant declaration initializer or be initialized by constant
blocking assignments in an initial block. Constant expressions, localparams, and whole-array
declaration assignment patterns are supported. Bounded constant for loops may initialize array
elements. Every persistent clocked register must have all bits initialized or all bits reset in
the task's if (rst) branch. Partial initialization and partial reset cannot be combined to
satisfy this rule. Repeated assignments in one initial block execute in order. Overlapping
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
call. Functions cannot retain history between calls; keep monitor history at module scope,
with the required initialization or reset. Local declaration initializers in automatic
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
Parser output is limited to 4 MiB and 12,000 syntax elements; each expanded checker variant is
limited to 1 MiB. Follow the task's initialization, reset, timing, and parameter profile. When
you receive feedback, return the complete corrected checker.

```systemverilog
module rtl_checker #(
    parameter integer W = 2,
    parameter integer DEPTH = 4
) (
    input logic clk,
    input logic rst,
    input logic wr_en,
    input logic [W-1:0] din,
    input logic rd_en,
    input logic [W-1:0] dout,
    input logic full,
    input logic empty,
    input logic [$clog2(DEPTH):0] count
);
    // Add immediate assertions and monitor state.
endmodule
```

This verification profile fixes `W=2` and `DEPTH=4`. All data words are
unsigned. A write occurs on a nonreset rising edge when `wr_en=1` and
the FIFO was not full before that edge. Append `din` to the tail.
A read occurs when `rd_en=1` and the FIFO was not empty before that
edge. Remove the oldest word and register it on `dout`.

The decision on each operation uses occupancy before the edge. A write
while full is ignored even if a read occurs. A read while empty is ignored
even if a write occurs. Simultaneous accepted read and write preserve
occupancy and preserve the order of every retained word. Requests may be
asserted regardless of the flags.

After every edge, `count` is the number of retained words,
`empty=(count==0)` and `full=(count==4)`. These flags and count are
meaningful on every cycle. A reset edge empties the FIFO, ignores both
requests and establishes count zero, full zero and empty one.

Data is meaningful only in the cycle immediately following a successful
read. In that cycle `dout` must equal the removed oldest word. In all
other cycles, including after reset and after an ignored read,
`dout` is unspecified. A correct implementation may retain its prior
data, drive zero, expose storage, or choose another value in those cycles.

The formal profile unrolls 12 transitions and adds one final observation.
Reset is high on the first transition and low thereafter. Implementation
registers and storage are unrestricted before reset. Suppress assertions
until reset has established the starting state. The observer must check
`dout` only when a successful read occurred on the preceding transition.
