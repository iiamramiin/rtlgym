# Three-cycle signed multiplier

Implement a signed, full-precision multiplier with one input slot per cycle. The
default multiplies two 16-bit operands and produces a 32-bit result.

```systemverilog
module mul_pipe3 #(
    parameter integer WIDTH = 16
) (
    input  logic                      clk,
    input  logic                      rst,
    input  logic                      in_valid,
    input  logic signed [WIDTH-1:0]   a,
    input  logic signed [WIDTH-1:0]   b,
    output logic                      out_valid,
    output logic signed [2*WIDTH-1:0] product
);
```

- `WIDTH` is at least 2. Interpret both operands and the product as two's-complement
  integers. Compute the exact signed product in `2*WIDTH` bits, including the
  product of the two most-negative operands. There is no saturation or rounding.
- A rising edge with `rst=0` and `in_valid=1` accepts one pair. A pair accepted
  at rising edge `k` appears with `out_valid=1` and its product immediately
  after rising edge `k+3`, three clock periods after acceptance. For example,
  consecutive pairs accepted at edges 0 and 1 produce results after edges 3
  and 4, respectively.
- A low `in_valid` inserts a bubble at the corresponding output edge even
  when the operands happen to repeat. Drive `product=0` whenever `out_valid=0`.
  There is no ready signal. The input may change every cycle.
- Reset is synchronous and active high. On a rising edge with `rst=1`, discard all
  pending products, ignore the inputs, and drive `out_valid=0` and `product=0`.
  The next edge with `rst=0` can accept a new pair.
