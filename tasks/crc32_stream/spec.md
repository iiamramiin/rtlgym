# Streaming Ethernet CRC-32

Compute the CRC-32 of the byte stream received since the last reset or start.
The source can provide one byte per cycle, with optional gaps.

```systemverilog
module crc32_stream (
    input  logic        clk,
    input  logic        rst,
    input  logic        start,
    input  logic        in_valid,
    input  logic [7:0]  data,
    output logic        out_valid,
    output logic [31:0] crc
);
```

All inputs are sampled on the rising edge of `clk`. The outputs immediately
after that edge belong to the following cycle. The CRC for a byte offered in
cycle `n` is available with `out_valid = 1` in cycle `n+1`. Consecutive input
bytes produce consecutive valid output cycles. There is no backpressure and
no explicit end-of-frame input. Each accepted byte produces the CRC of the
prefix through that byte, so the value after the last byte is the frame CRC.

1. If `rst` is high, reset takes priority over all other inputs. Set the
   internal remainder to `32'hFFFF_FFFF`, drive `crc = 0` and
   `out_valid = 0`, and ignore the byte. Reset is synchronous.
2. Otherwise choose the initial remainder for this cycle. If `start` is high,
   use `32'hFFFF_FFFF` regardless of the previous CRC. Otherwise use the
   previous internal remainder. A high `start` begins a new stream at every
   edge where it is sampled, including consecutive edges.
3. If `in_valid` is high, consume `data` starting from the remainder chosen in
   step 2, then assert `out_valid`. When `start` is also high, this byte is the
   first byte of the new stream, even if it is zero. If `in_valid` is low,
   ignore `data`, retain the remainder chosen in step 2, and clear
   `out_valid`. A start without a valid byte therefore sets `crc` to zero.
   A gap with neither input high holds `crc` unchanged.

Process the bytes in arrival order. Within each byte process bit 0 first,
then bits 1 through 7. For each bit, compute `mix = remainder[0] XOR bit`,
shift the 32-bit remainder right by one with zero fill, then XOR
`32'hEDB8_8320` into it if `mix` was 1. The `crc` output is always the
current remainder XOR `32'hFFFF_FFFF`. Apply the final XOR only to the
output. Output the numerical CRC directly without swapping its bytes.
For the nine ASCII bytes of `123456789`, the final output is
`32'hCBF4_3926`.
