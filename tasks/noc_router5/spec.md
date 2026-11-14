# Five-port XY mesh router

Route single-flit packets through one router of a 2D mesh. Both sides use ready/valid handshakes. Each output has one registered flit slot and arbitrates independently.

```systemverilog
module noc_router5 #(
    parameter logic [1:0] X = 2'd1,
    parameter logic [1:0] Y = 2'd1,
    parameter int PAYLOAD_W = 8
) (
    input  logic                       clk,
    input  logic                       rst,
    input  logic [4:0]                 in_valid,
    output logic [4:0]                 in_ready,
    input  logic [5*(4+PAYLOAD_W)-1:0]  in_flit,
    output logic [4:0]                 out_valid,
    input  logic [4:0]                 out_ready,
    output logic [5*(4+PAYLOAD_W)-1:0]  out_flit
);
```

Lane indices 0 through 4 are N, S, E, W and L (local). With `F = 4 + PAYLOAD_W`, lane `i` occupies bits `[i*F +: F]` of each flit bus. Its fields from most to least significant are `{dest_x[1:0], dest_y[1:0], payload[PAYLOAD_W-1:0]}`. Coordinates are unsigned. Support any 2-bit local coordinates and any positive payload width. A valid input can request any of the five outputs, including the one with the same index.

## Routing

For each valid input, in order:

1. If `dest_x > X`, request E. If `dest_x < X`, request W.
2. If X coordinates match, request N when `dest_y > Y` or S when `dest_y < Y`.
3. If both coordinates match, request L.

Forward the complete original flit, including both destination fields.

## Timing and arbitration

- A transfer occurs on a rising edge with both valid and ready high on the same lane, with reset low. An upstream source holds a pending valid flit stable until accepted. A downstream consumer can change ready from cycle to cycle.
- An output slot is available when empty or when its current flit will transfer on the upcoming edge. An unavailable slot admits no new flit. There is no combinational flit or valid bypass from input to output. An input accepted at an edge is observable at its output immediately after that edge and can first transfer at the next rising edge.
- Each available output chooses at most one valid requester. Scan in cyclic order N, S, E, W, L, starting at that output's cursor. Choose the first requester, skipping absent requests and wrapping as needed. Only the chosen input has `in_ready` high. Every input with `in_valid` low has `in_ready` low. Outputs may accept in parallel.
- The cursor starts at N and advances to the successor of the source of the retiring flit **only on a completed output transfer**. If a slot drains and refills on the same edge, choose the incoming flit using the retiring source's successor on that edge. If a flit from W is retiring, for example, the scan starts at L even for an immediately following replacement. Hold the cursor while idle or stalled.
- If a slot accepts a new flit, it becomes valid and stores that flit. Otherwise, a drain empties it. An occupied slot that does not drain keeps valid and its flit unchanged. Drive every invalid output lane's flit bits to zero.
- `rst` is active high and synchronous. While asserted, all input ready bits are zero and there are no transfers. A rising edge with reset asserted empties all five slots and resets all cursors to N. Output valid and flit signals otherwise reflect the registered slots, including before the first reset edge.
