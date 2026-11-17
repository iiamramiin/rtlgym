# Verify a synchronous FIFO

Write a SystemVerilog observer named `rtl_checker` containing immediate
assertions. Every port is an input. Observe only these ports. You may keep
internal monitor state and compute expected values from input history.
Return the complete observer module. The judge supplies the implementation.

A checker is scored by the fraction of distinct incorrect behaviors it detects.
It must accept every correct implementation. A false alarm on any correct
implementation earns zero. Source errors and inconclusive proofs earn zero.

Use `always_comb` or `always @*` for combinational checks. For sequential
checks, use `always @(posedge clk)`. At that event the observed outputs are
the state produced by the previous clock edge. Assertions execute before
the implementation and monitor update their registers. Reconstruct expected
outputs using that same observation convention.

The observer may use arithmetic, comparisons, loops, functions and local
registers. Do not instantiate modules, drive an observed port, reference
implementation internals, constrain the inputs, include files, or use system
tasks. Use immediate `assert (...);` statements. The fixed profile below
defines the parameter values and bounded history used for grading.

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
