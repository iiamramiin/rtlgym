# 16-to-12 streaming gearbox

Convert a stream of 16-bit words into a stream of 12-bit words on one clock.
Both interfaces use ready/valid handshakes. Maintain the order of all bits
through stalls and across word boundaries.

```systemverilog
module gearbox_16to12 #(
    parameter integer UNIT_W = 4
) (
    input  logic                clk,
    input  logic                rst,
    input  logic                in_valid,
    output logic                in_ready,
    input  logic [4*UNIT_W-1:0] in_data,
    output logic                out_valid,
    input  logic                out_ready,
    output logic [3*UNIT_W-1:0] out_data
);
```

`UNIT_W` is a positive integer. The default is four bits per unit, so each
input carries four nibbles and each output carries three. Number units within a
word starting at the least significant unit. The units of an input at indices
0, 1, 2, and 3 are appended in that order. The oldest three buffered units
form output units 0, 1, and 2, respectively. Preserve the bit order within
a unit. For example, an input `16'h3210` followed by `16'h7654` yields
`12'h210`, then `12'h543`, with units 6 and 7 still waiting for another unit.

## Clock and handshakes

- The buffer holds at most eight units. Let `n` be its occupancy immediately
  before a rising clock edge. Drive `out_valid = (n >= 3)`. If valid, drive
  the oldest three units on `out_data`. Otherwise drive `out_data = 0`.
  Input bits do not bypass the buffer to the output.
- When reset is low, an output transfers on an edge with `out_valid &&
  out_ready`. That transfer removes three units. Drive `in_ready` high when
  there is room for four new units **after** accounting for an output transfer
  on that same edge. In particular, an output transfer can make room for an
  input that otherwise would have been stalled.
- An input transfers on an edge with `in_valid && in_ready`. If both sides
  transfer, remove the oldest three units first and append the new four units
  behind all remaining units. Updates become visible immediately after the
  edge. A stalled valid output holds its data even if more input is accepted.
  The source holds a word and its valid flag until the word transfers.
- One or two buffered units wait indefinitely for enough input to form the
  next output word. There is no partial-word transfer or end marker.
- Reset is synchronous, active high. While `rst` is high, drive `in_ready=0`
  and ignore handshakes. At a rising edge with reset high, discard all buffered
  units. After that edge `out_valid=0` and `out_data=0`. A word can be accepted
  on the first rising edge with reset low.
