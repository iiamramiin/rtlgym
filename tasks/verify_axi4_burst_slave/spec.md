# Verify an AXI4 burst memory slave with bounded timing freedom

Write a port-only checker for the following small AXI4 memory-slave profile. The
DUT implementation is hidden. Judge accepted transfers, retained data and protocol
obligations rather than copying one implementation's ready/response schedule.

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
    parameter int ADDR_W = 3,
    parameter int ID_W   = 1,
    parameter int LEN_W  = 1
) (
    input  logic              clk,
    input  logic              rst,

    input  logic [ID_W-1:0]   s_axi_awid,
    input  logic [ADDR_W-1:0] s_axi_awaddr,
    input  logic [LEN_W-1:0]  s_axi_awlen,
    input  logic [2:0]        s_axi_awsize,
    input  logic [1:0]        s_axi_awburst,
    input  logic              s_axi_awlock,
    input  logic [3:0]        s_axi_awcache,
    input  logic [2:0]        s_axi_awprot,
    input  logic [3:0]        s_axi_awqos,
    input  logic [3:0]        s_axi_awregion,
    input  logic              s_axi_awvalid,
    input  logic              s_axi_awready,

    input  logic [31:0]       s_axi_wdata,
    input  logic [3:0]        s_axi_wstrb,
    input  logic              s_axi_wlast,
    input  logic              s_axi_wvalid,
    input  logic              s_axi_wready,

    input  logic [ID_W-1:0]   s_axi_bid,
    input  logic [1:0]        s_axi_bresp,
    input  logic              s_axi_bvalid,
    input  logic              s_axi_bready,

    input  logic [ID_W-1:0]   s_axi_arid,
    input  logic [ADDR_W-1:0] s_axi_araddr,
    input  logic [LEN_W-1:0]  s_axi_arlen,
    input  logic [2:0]        s_axi_arsize,
    input  logic [1:0]        s_axi_arburst,
    input  logic              s_axi_arlock,
    input  logic [3:0]        s_axi_arcache,
    input  logic [2:0]        s_axi_arprot,
    input  logic [3:0]        s_axi_arqos,
    input  logic [3:0]        s_axi_arregion,
    input  logic              s_axi_arvalid,
    input  logic              s_axi_arready,

    input  logic [ID_W-1:0]   s_axi_rid,
    input  logic [31:0]       s_axi_rdata,
    input  logic [1:0]        s_axi_rresp,
    input  logic              s_axi_rlast,
    input  logic              s_axi_rvalid,
    input  logic              s_axi_rready
);
    // Add immediate assertions and private monitor state.
endmodule
```

The profile fixes ADDR_W=3, ID_W=1 and LEN_W=1: eight bytes arranged as two
32-bit words, one-bit transaction IDs, and one or two beats per burst. All inputs
may change arbitrarily on every edge; only VALID && READY at a nonreset rising
edge transfers a channel. No assumptions about a cooperative master are needed.
Reset is high on the first of eight transitions and low afterwards. There is one
final observation, for nine sampled states. Suppress history-dependent checks
until reset has established the DUT state.

A descriptor is legal exactly when its address is divisible by four, SIZE=2,
BURST=01, LOCK=0, and the integer final byte address ADDR+4*LEN is less than eight.
CACHE, PROT, QOS and REGION do not affect the transaction. Each descriptor always
has LEN+1 beats, even when invalid. No transaction IDs are reordered.

Writes: accept one AW descriptor, then LEN+1 W beats. WREADY must be low without
a captured write. AWREADY must be low while collecting W beats or retaining its
B response. On a legal write, each accepted W beat updates enabled byte lanes at
ADDR+4*beat; disabled lanes retain their values. An invalid descriptor writes
nothing. WLAST must be zero on nonfinal beats and one on the final beat; any
mismatch changes BRESP to SLVERR but does not end the burst or suppress legal
writes. After the final W beat, issue exactly one B response with captured AWID
and OKAY=00 for a legal descriptor with correct WLAST, otherwise SLVERR=10. Hold
BVALID, BID and BRESP unchanged until BREADY accepts the response. Do not accept
a new AW on the same edge that consumes the preceding B response.

Reads: accept one AR descriptor only when no read burst remains. Return LEN+1
R beats with captured ARID, RLAST only on the final beat, and RRESP=OKAY for a
legal descriptor. A legal first beat snapshots its word before the AR handshake
edge. Each later beat snapshots the next word before the edge accepting the
preceding R beat. Simultaneous W writes become visible only to later snapshots.
An invalid read returns SLVERR and zero data on every beat. Once RVALID is raised,
hold RVALID and the entire R payload unchanged until RREADY accepts it. Do not
accept a new AR on the edge consuming the preceding final R beat.

Timing freedom is deliberate. When eligible to accept AW, W or AR, READY may be
withheld for one cycle, but not two consecutive eligible cycles. It may depend on
private scheduler state. A response beat becomes eligible after the corresponding
last W handshake, AR handshake, or preceding nonfinal R handshake. Its VALID may
appear immediately in the following sampled state or one state later. Once VALID
appears it cannot be withdrawn before acceptance. These bounds hold independently
of input VALID or response READY. Write and read engines proceed independently.
When BVALID or RVALID is low, that channel's payload is unspecified: it may retain
a prior value, become zero, or change for another implementation.

A reset edge cancels every transaction, clears BVALID and RVALID and zeroes all
eight memory bytes. Reset suppresses AWREADY, WREADY and ARREADY. Payload outputs
while their VALID is low are unspecified, including after reset. The grader checks
several correct designs with different ready throttling, response delays and
idle payload values. A checker that requires exact timing or idle payloads will
raise a false alarm.

A complete grading attempt has a 60-second tool budget. Exhaustion is
inconclusive, earns zero and is not cached. Each individual proof also has a
15-second limit.
