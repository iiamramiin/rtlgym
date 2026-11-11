# seq_detect_1011

Detect the bit pattern `1011` in a serial stream, with overlapping matches.

## Interface

```systemverilog
module seq_detect_1011 (
    input  logic clk,
    input  logic rst,    // synchronous, active high
    input  logic din,    // serial input, one bit per clock
    output logic match
);
```

## Behavior

- One bit of `din` is sampled on every rising edge of `clk`, oldest bit first.
- When the last four sampled bits, in arrival order, are `1, 0, 1, 1`, `match`
  is 1 for exactly the next clock cycle (it is a register output, updated on the
  same rising edge that samples the final `1`).
- Matches may overlap: the stream `1 0 1 1 0 1 1` contains two matches,
  because the `1` that ends the first match also starts the second.
- `rst == 1` on a rising edge clears all history and `match`; bits sampled
  before a reset never contribute to a match after it.
