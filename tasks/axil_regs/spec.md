# AXI4-Lite peripheral registers

Implement a single-clock 32-bit AXI4-Lite slave. All five channels use the
`VALID`/`READY` handshake: a transfer occurs on a rising `clk` edge with both
signals high. Addresses are four-bit byte offsets. Protection inputs are
accepted and ignored.

```systemverilog
module axil_regs (
    input  logic        clk,
    input  logic        rst,
    input  logic [31:0] status_in,
    input  logic [31:0] irq_set,

    input  logic [3:0]  s_axi_awaddr,
    input  logic [2:0]  s_axi_awprot,
    input  logic        s_axi_awvalid,
    output logic        s_axi_awready,

    input  logic [31:0] s_axi_wdata,
    input  logic [3:0]  s_axi_wstrb,
    input  logic        s_axi_wvalid,
    output logic        s_axi_wready,

    output logic [1:0]  s_axi_bresp,
    output logic        s_axi_bvalid,
    input  logic        s_axi_bready,

    input  logic [3:0]  s_axi_araddr,
    input  logic [2:0]  s_axi_arprot,
    input  logic        s_axi_arvalid,
    output logic        s_axi_arready,

    output logic [31:0] s_axi_rdata,
    output logic [1:0]  s_axi_rresp,
    output logic        s_axi_rvalid,
    input  logic        s_axi_rready
);
```

## Register map

| Address | Register | Read | Write |
| --- | --- | --- | --- |
| `0x0` | CTRL | Stored 32-bit value | Replace enabled bytes |
| `0x4` | STATUS | Sample `status_in` | Reject with SLVERR |
| `0x8` | SCRATCH | Stored 32-bit value | Replace enabled bytes |
| `0xC` | IRQ | Stored pending bits | Write one to clear enabled bits |

Successful accesses return OKAY (`2'b00`). All other addresses, including
unaligned offsets, return SLVERR (`2'b10`). An invalid read returns zero data.
A rejected write makes no write-driven state changes. Each `WSTRB[i]` enables
byte `WDATA[8*i +: 8]`. Disabled bytes are unaffected, and a valid writable
address with all strobes low returns OKAY without changing the register.

On every non-reset edge, `irq_set` is ORed into the IRQ bits, regardless of bus
activity. On an IRQ write commit edge, clear precisely the bits where both the
written data bit and its byte strobe are one. A set on the same edge takes
priority over clearing that bit. Equivalently, the next IRQ value is
`(old_irq & ~clear_mask) | irq_set`. A zero written to a bit leaves it unchanged
unless the pulse sets it.

## Channel timing

- The slave accepts at most one write and one read in flight, independently.
  The write address and write data each have a separate one-entry slot, so they
  can arrive in either order or on the same edge. `AWREADY` and `WREADY` are
  high exactly when their respective slot is empty, `BVALID` is low, and
  `rst` is low. A received half stays unchanged until its write commits.
- On the rising edge **after** both write halves have been received, apply the
  write and register `BVALID=1` and `BRESP`. This is the commit edge. Neither
  write channel can accept another transfer until after the response handshake.
- `ARREADY` is high exactly when `RVALID` and `rst` are both low. On an AR
  handshake, capture the addressed register value and response, and assert
  `RVALID` just after that same edge. A read observes the old register state
  when it coincides with a write commit or an IRQ set. STATUS samples its
  external input at the AR handshake.
- A pending B or R response remains valid with its response fields stable until
  its corresponding handshake. At the handshake edge, clear the valid flag.
  No new request of that direction can be accepted at a response handshake
  edge. Invalid responses retain their last payload and response code until a
  new response or reset.

## Reset

`rst` is active high. It suppresses all three ready signals while asserted.
At a rising edge with `rst=1`, abandon partial requests and pending responses,
ignore `irq_set`, clear CTRL, SCRATCH and IRQ, and set `BVALID`, `RVALID`,
`RDATA`, `BRESP` and `RRESP` to zero.
