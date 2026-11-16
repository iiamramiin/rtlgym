# AXI4 burst memory slave

Implement a memory slave for the aligned, 32-bit INCR subset of AXI4. It has
five independent channels and can service one write burst and one read burst
concurrently. Each channel transfers on a rising edge of `clk` with both its
VALID and READY high. In the default configuration the address, transaction ID
and AXI4 LEN fields are eight, two and eight bits, respectively.

```systemverilog
module axi4_burst_slave #(
    parameter int ADDR_W = 8,
    parameter int ID_W   = 2,
    parameter int LEN_W  = 8
) (
    input  logic              clk,
    input  logic              rst,

    input  logic [ID_W-1:0]   s_axi_awid,
    input  logic [ADDR_W-1:0] s_axi_awaddr,
    input  logic [LEN_W-1:0]  s_axi_awlen,
    input  logic [2:0]        s_axi_awsize,
    input  logic [1:0]        s_axi_awburst,
    input  logic              s_axi_awlock,
    input  logic [3:0]        s_axi_awcache,
    input  logic [2:0]        s_axi_awprot,
    input  logic [3:0]        s_axi_awqos,
    input  logic [3:0]        s_axi_awregion,
    input  logic              s_axi_awvalid,
    output logic              s_axi_awready,

    input  logic [31:0]       s_axi_wdata,
    input  logic [3:0]        s_axi_wstrb,
    input  logic              s_axi_wlast,
    input  logic              s_axi_wvalid,
    output logic              s_axi_wready,

    output logic [ID_W-1:0]   s_axi_bid,
    output logic [1:0]        s_axi_bresp,
    output logic              s_axi_bvalid,
    input  logic              s_axi_bready,

    input  logic [ID_W-1:0]   s_axi_arid,
    input  logic [ADDR_W-1:0] s_axi_araddr,
    input  logic [LEN_W-1:0]  s_axi_arlen,
    input  logic [2:0]        s_axi_arsize,
    input  logic [1:0]        s_axi_arburst,
    input  logic              s_axi_arlock,
    input  logic [3:0]        s_axi_arcache,
    input  logic [2:0]        s_axi_arprot,
    input  logic [3:0]        s_axi_arqos,
    input  logic [3:0]        s_axi_arregion,
    input  logic              s_axi_arvalid,
    output logic              s_axi_arready,

    output logic [ID_W-1:0]   s_axi_rid,
    output logic [31:0]       s_axi_rdata,
    output logic [1:0]        s_axi_rresp,
    output logic              s_axi_rlast,
    output logic              s_axi_rvalid,
    input  logic              s_axi_rready
);
```

`ADDR_W` may be 3 through 12, `ID_W` may be 1 through 8, and `LEN_W` may be 1
through 8. The memory holds `2**ADDR_W` bytes, addressed from zero, with byte
lane zero in bits [7:0] of a word. CACHE, PROT, QOS and REGION are ignored. A
legal burst requires SIZE=2 (4 bytes), BURST=01 (INCR), LOCK=0, and an address
divisible by four. Its final word at the integer address `ADDR + 4*LEN` must
be inside the memory. Every burst contains exactly `LEN+1` data beats; beat
zero uses ADDR and subsequent beats advance the address by four. This device
does not support exclusive, narrow, FIXED, or WRAP transactions.

## Writes

- AWREADY is high when reset is low and there is no captured write or pending
  B response. An AW handshake latches the descriptor and ID. WREADY is high
  while reset is low and that write is collecting beats. A W request may be
  presented before AW, but is accepted only after AW has been captured.
- For each accepted W beat of a legal burst, enable byte lane `i` only when
  WSTRB[i] is high. Leave disabled bytes unchanged. A zero strobe is a no-op.
  Each write takes effect on the W handshake edge.
- Consume exactly LEN+1 W beats based on the captured AWLEN. WLAST must be
  zero before the final beat and one on the final beat. Record a mismatch
  on any accepted beat. A mismatch does not change which beats are consumed
  or which bytes are written for a legal descriptor.
- After the last expected W handshake, register BVALID=1, BID from the captured
  AWID, and BRESP=OKAY (00) for a legal burst with no WLAST mismatch. An invalid
  descriptor consumes the same number of beats, writes no memory and returns
  SLVERR (10). Any WLAST mismatch also returns SLVERR.
- Hold BVALID, BID and BRESP through backpressure. Clear BVALID on a B handshake.
  AW and W cannot handshake on the edge that consumes B.

## Reads

- ARREADY is high when reset is low and there is no pending R beat. Capture the
  complete AR descriptor at its handshake. Immediately after that edge,
  register the first beat with RVALID=1. RID is the captured ARID on every beat.
- For a legal burst, RRESP=OKAY and RDATA holds the word at the current address.
  For an invalid descriptor, every beat has RRESP=SLVERR and RDATA=0.
- Hold RVALID, RID, RRESP, RLAST and RDATA unchanged until the R handshake. On
  a handshake for a nonfinal beat, register the next beat immediately after the
  edge, with no idle cycle. RLAST is high precisely for the last of the LEN+1
  beats. On the final handshake, clear RVALID. A new AR cannot handshake on this
  same edge.
- Each R beat samples memory as it stood **before** the edge that produces it.
  A simultaneous W handshake to the same word is visible to later reads.
  Stalling R never changes a previously sampled word.
- While BVALID or RVALID is low, retain that channel's most recent payload and
  response outputs until replacement or reset.

## Reset

`rst` is active high and suppresses AWREADY, WREADY and ARREADY immediately.
A rising clock edge with `rst=1` cancels all partially serviced transactions,
zeros every memory word, clears BVALID and RVALID, and sets BID, BRESP, RID,
RRESP, RLAST and RDATA to zero. Ignore all channel transfers on reset edges.
