# Verify a combinational population count

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
