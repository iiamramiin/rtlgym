# up_down_counter

An 8-bit loadable up/down counter with synchronous reset.

## Interface

```systemverilog
module up_down_counter (
    input  logic       clk,
    input  logic       rst,   // synchronous, active high
    input  logic       en,
    input  logic       up,    // 1 = count up, 0 = count down
    input  logic       load,
    input  logic [7:0] d,
    output logic [7:0] q
);
```

## Behavior

All updates happen on the rising edge of `clk`, in this priority order:

1. `rst == 1`: `q <= 0`.
2. else `load == 1`: `q <= d` (regardless of `en`).
3. else `en == 1`: `q <= q + 1` if `up`, else `q <= q - 1`. The counter wraps
   (255 + 1 = 0, 0 - 1 = 255).
4. else `q` holds its value.

`q` is a register output (it changes only on clock edges).
