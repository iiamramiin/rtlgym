# Verify a combinational population count

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
module rtl_checker (
    input logic [15:0] x,
    input logic [4:0] count
);
    // Add immediate assertions.
endmodule
```

For every 16-bit input `x`, `count` must equal the number of its set bits.
The numerical output is 0 through 16. This circuit is combinational and
has no clock or reset. Inputs are unrestricted. The formal profile checks
every input combination with these exact widths.
