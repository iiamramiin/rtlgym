# Streaming Internet checksum

Compute the 16-bit one's-complement checksum of each packet in a byte
stream. Each packet has at least one byte. The end-of-packet flag travels
with the final byte. The design may use helper modules in the same file,
for example to pack bytes and to fold the running sum.

```systemverilog
module packet_checksum #(
    parameter integer BYTE_W = 8
) (
    input  logic                  clk,
    input  logic                  rst,
    input  logic                  in_valid,
    output logic                  in_ready,
    input  logic [BYTE_W-1:0]     in_data,
    input  logic                  in_last,
    output logic                  out_valid,
    input  logic                  out_ready,
    output logic [2*BYTE_W-1:0]  out_checksum
);
```

`BYTE_W` can be any integer from one to eight. At its default, an input byte has
eight bits and the checksum has sixteen. For other values use the same
algorithm on two-unit words of width `2*BYTE_W`.

## Arithmetic

Start with a sum of zero for each packet. Pair consecutive input bytes into
words, first byte in the upper half. For an odd-length packet, pad the
last word with an all-zero lower half. For each word, add it to the running
sum using one extra bit. Add the carry out back to the low bits of the sum.
Return the bitwise inverse of the final folded sum. For example, bytes
`12 34 56` (hex) produce words `1234` and `5600`, folded sum
`6834`, and checksum `97CB`. Output the numerical checksum as is,
including either all-zero or all-one results.

## Handshakes

- All transfers occur on the rising edge of `clk` with reset low and valid
  and ready high for that side. The source holds `in_data` and `in_last`
  stable until a valid input transfers. An accepted byte with `in_last=1`
  ends the packet, and the next accepted byte starts a new packet.
- Buffer one completed checksum. When reset is low, drive `in_ready=1`
  for any nonfinal input byte. For `in_last=1`, drive `in_ready=1` only
  when the output slot is empty or its current checksum will transfer on
  the upcoming edge. This ready rule applies even when `in_valid=0`.
  Nonfinal bytes of a new packet may accumulate while the output stalls.
- Immediately after accepting a final byte, make its checksum and
  `out_valid=1` visible. On a simultaneous output transfer, the outgoing
  checksum is the previous packet's and the new checksum takes its place.
  While `out_valid=1` and `out_ready=0`, hold the checksum and valid flag.
  With no pending checksum, drive `out_valid=0` and `out_checksum=0`.
- Reset is synchronous and active high. Suppress `in_ready` while reset is
  high. A reset edge discards any partial packet and pending checksum,
  clears the output, and ignores input. The first non-reset edge may
  accept a byte.
