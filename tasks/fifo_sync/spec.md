# fifo_sync

A synchronous FIFO (single clock) with registered read data.

## Interface

```systemverilog
module fifo_sync #(
    parameter int W     = 8,   // data width
    parameter int DEPTH = 8    // number of entries, a power of 2
) (
    input  logic                   clk,
    input  logic                   rst,     // synchronous, active high
    input  logic                   wr_en,
    input  logic [W-1:0]           din,
    input  logic                   rd_en,
    output logic [W-1:0]           dout,
    output logic                   full,
    output logic                   empty,
    output logic [$clog2(DEPTH):0] count
);
```

The testbench uses the default parameters (W = 8, DEPTH = 8, so `count` is 4 bits).

## Behavior

All state changes on the rising edge of `clk`.

- `rst == 1`: the FIFO becomes empty (`count = 0`). The value of `dout` after reset
  is not checked.
- A **write** happens when `wr_en == 1` and `full == 0`: `din` is stored at the tail.
  A write while `full == 1` is ignored, even if a read happens in the same cycle.
- A **read** happens when `rd_en == 1` and `empty == 0`: the oldest entry is
  removed and appears on `dout` after that rising edge (registered output).
  A read while `empty == 1` is ignored, even if a write happens in the same cycle.
- When a read does not happen, `dout` holds its previous value.
- A write and a read can both happen in the same cycle; `count` is then unchanged.
- `count` is the number of stored entries (0 to DEPTH). `full` is `count == DEPTH`
  and `empty` is `count == 0`. These three outputs reflect the state after the
  most recent rising edge.
