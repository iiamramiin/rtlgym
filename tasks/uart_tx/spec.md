# uart_tx

A UART transmitter: 8 data bits, no parity, 1 stop bit (8N1).

## Interface

```systemverilog
module uart_tx #(
    parameter int CLKS_PER_BIT = 4   // clock cycles per UART bit, >= 2
) (
    input  logic       clk,
    input  logic       rst,     // synchronous, active high
    input  logic       start,
    input  logic [7:0] data,
    output logic       tx,
    output logic       busy
);
```

The testbench uses the default `CLKS_PER_BIT = 4`.

## Behavior

All outputs are registered and change only on rising edges of `clk`.

- **Idle:** `tx = 1`, `busy = 0`. After reset the transmitter is idle.
- **Start:** on a rising edge where `start == 1` and `busy == 0`, the module
  captures `data` and begins a frame on that same edge: `tx <= 0` (start bit) and
  `busy <= 1`.
- **Frame:** the frame is 10 bits: start bit `0`, then `data[0]` through
  `data[7]` (LSB first), then stop bit `1`. Each bit is driven on `tx` for exactly
  `CLKS_PER_BIT` clock cycles. So `tx` shows the start bit for the
  `CLKS_PER_BIT` cycles following the start edge, and so on.
- **End:** `busy` stays 1 for the whole frame, `10 * CLKS_PER_BIT` cycles in
  total. On the rising edge that ends the stop bit, `busy <= 0` and `tx` stays 1.
  A new `start` can be accepted on the next rising edge.
- `start` is ignored while `busy == 1`, and changes on `data` during a frame do
  not affect the frame in progress.
- `rst == 1` on a rising edge returns to idle (`tx <= 1`, `busy <= 0`) immediately,
  even mid-frame.
