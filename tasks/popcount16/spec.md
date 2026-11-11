# popcount16

Combinational population count: output the number of `1` bits in a 16-bit input.

## Interface

```systemverilog
module popcount16 (
    input  logic [15:0] x,
    output logic [4:0]  count
);
```

## Behavior

- `count` equals the number of bits of `x` that are `1` (0 to 16).
- Purely combinational: no clock, no state.

## Quality

Once correct, smaller logic (fewer gates, shallower logic depth) scores higher.
