# rr_arbiter4

A 4-requester round-robin arbiter with a registered one-hot grant.

## Interface

```systemverilog
module rr_arbiter4 (
    input  logic       clk,
    input  logic       rst,   // synchronous, active high
    input  logic [3:0] req,
    output logic [3:0] gnt
);
```

## Behavior

- The arbiter keeps `last`, the index (0 to 3) of the most recent requester it
  granted. After reset, `last = 3`, so requester 0 has the highest priority first.
- On every rising edge with `rst == 0`:
  - If `req == 0`: `gnt <= 0` and `last` is unchanged.
  - Otherwise, search the indices `last+1, last+2, last+3, last+4` (all modulo 4)
    and pick the first `i` with `req[i] == 1`. Then `gnt <= 4'b1 << i` and
    `last <= i`.
- `rst == 1` on a rising edge: `gnt <= 0`, `last <= 3`.
- A new decision is made every cycle; a grant is not held across cycles. `gnt`
  is always zero or one-hot, and is a register output.
