# edge_detect

Detect rising and falling edges of a 1-bit input, with registered outputs.

## Interface

```systemverilog
module edge_detect (
    input  logic clk,
    input  logic rst,   // synchronous, active high
    input  logic din,
    output logic rise,
    output logic fall
);
```

## Behavior

The module samples `din` on every rising edge of `clk`. Let `prev` be the value
of `din` sampled at the previous rising edge (0 after reset).

On each rising edge, when `rst == 0`:

- `rise <= din & ~prev`
- `fall <= ~din & prev`
- `prev <= din`

When `rst == 1`, `rise`, `fall` and `prev` are all cleared to 0 on the rising
edge.

So a 0-to-1 change on `din` produces a one-cycle pulse on `rise` that appears
in the clock cycle after the edge where the new value was first sampled.
`rise` and `fall` are register outputs.
