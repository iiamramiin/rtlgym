# Asynchronous FIFO

Store words between independent write and read clock domains using a dual-port buffer with Gray-coded crossing pointers.

```systemverilog
module async_fifo #(
    parameter int W = 8,
    parameter int DEPTH = 8
) (
    input  logic         wr_clk,
    input  logic         rd_clk,
    input  logic         rst,
    input  logic         wr_en,
    input  logic [W-1:0] din,
    output logic         full,
    input  logic         rd_en,
    output logic [W-1:0] dout,
    output logic         empty
);
```

`W` is positive. `DEPTH` is a power of two, at least two, and is the number of usable words. The two clocks may have any relative frequency and phase, including coincident rising edges. There is no combinational path from one clock domain's inputs or local pointer to the other domain's flags.

## Transfers and reset

- At a rising `wr_clk` edge with reset low, enqueue `din` exactly when `wr_en=1` and the pre-edge `full=0`. Writes while full are ignored. The write enable and data are inputs synchronous to `wr_clk`.
- At a rising `rd_clk` edge with reset low, dequeue exactly when `rd_en=1` and the pre-edge `empty=0`. After a successful read, `dout` holds the dequeued word. Otherwise it holds its prior value. Reads while empty are ignored. `rd_en` is synchronous to `rd_clk`.
- Return words in enqueue order, exactly once. There is no write-through path to `dout`.
- `rst` is active high and sampled synchronously by both clocks. Hold it high until each clock has had at least one rising edge, and release it before a rising edge of either clock. A local reset edge takes precedence over transfers, flushes the corresponding local pointer and synchronizer stages to zero, and sets `full=0` in the write domain or `empty=1, dout=0` in the read domain. Old memory contents become inaccessible. Do not clear the storage array.

## Flag timing and clock-domain crossing

Each local transfer advances a pointer modulo `2*DEPTH`, including a wrap bit beyond the memory address. Register a Gray encoding of that pointer in its source domain. Only this registered Gray pointer crosses to the other domain, through two consecutive destination-clocked synchronizer stages. Mark the synchronizer stages for CDC placement if the tool supports it. Treat clocks, reset, and the crossing bus as physical CDC paths requiring implementation constraints.

Both flags are registered in their own clock domain. On each non-reset local rising edge, compute the next local pointer including any transfer accepted at that edge. Compute the new flag with that next local pointer and the **pre-edge** value of the second remote pointer synchronizer stage:

- `empty` is one when those read-domain pointers are equal.
- `full` is one when the next write pointer is `DEPTH` positions ahead of the synchronized read pointer modulo `2*DEPTH`.

Thus, in ideal RTL simulation a remote pointer update first participates in a destination flag calculation on the third destination rising edge strictly after that update. Coincident edges sample the old source pointer. The local pointer can still set a flag immediately after a local transfer. Conservative full or empty during remote-pointer propagation is expected. There is no special bypass on coincident write and read edges.
