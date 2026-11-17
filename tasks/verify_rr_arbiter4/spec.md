# Verify a registered round-robin arbiter

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
module rtl_checker (
    input logic clk,
    input logic rst,
    input logic [3:0] req,
    input logic [3:0] gnt
);
    // Add immediate assertions and monitor state.
endmodule
```

Maintain a priority cursor initially pointing to requester zero. On each
nonreset rising edge, choose the first asserted request in cyclic order
beginning at that cursor. The registered `gnt` after the edge is the one-hot
bit of the chosen requester. Advance the cursor to the requester after
the winner. If `req=0`, set the registered grant to zero and preserve
the cursor.

Reset is synchronous and active high. A reset edge makes the grant zero
and the cursor zero. Inputs are unrestricted, including changes to any
request between edges. There is a new decision every edge, with no
grant retention or backpressure.

The formal profile unrolls 12 transitions and adds one final observation
so a checker can observe the last registered result before its next
update. Reset is high on the first transition and low thereafter.
The initial values of implementation registers are unrestricted before
that reset. Suppress assertions until the reset edge has established
the starting state.
