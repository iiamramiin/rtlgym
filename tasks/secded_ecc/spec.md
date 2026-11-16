# Parameterized SECDED encoder and decoder

Implement a combinational extended Hamming code with separate encoder and decoder inputs.
The encoder and decoder operate independently and may be used at the same time.

```systemverilog
module secded_ecc #(
    parameter integer DATA_W = 16,
    localparam integer PARITY_W = (DATA_W <= 4) ? 3 : (DATA_W <= 11) ? 4
                                 : (DATA_W <= 26) ? 5 : 6
) (
    input  logic [DATA_W-1:0]          enc_data,
    output logic [DATA_W+PARITY_W:0]   enc_code,
    input  logic [DATA_W+PARITY_W:0]   dec_code,
    output logic [DATA_W-1:0]          dec_data,
    output logic                       corrected,
    output logic                       uncorrectable
);
```

Support every integer `DATA_W` from 4 through 32. `PARITY_W` is derived and
cannot be overridden. It is the smallest integer `P` for which
`2**P >= DATA_W + P + 1`. Set `H = DATA_W + PARITY_W`.
There is no clock or reset. All outputs depend on the current inputs.

## Encoding

The lower `H` bits are Hamming positions 1 through `H`. Position `p` is
bit `p-1` in both codeword ports. Positions `1, 2, 4, 8, ...` are check
bits. Fill the remaining positions in increasing order with `enc_data`
from bit 0 toward bit `DATA_W-1`.

For each `k` from 0 through `PARITY_W-1`, choose the check bit at position
`2**k` so the XOR of bits at all positions whose position number has bit
`k` set is zero. Set `enc_code[H]` to the XOR of `enc_code[H-1:0]`
so the entire codeword has even parity.

## Decoding

For each `k`, the XOR of the received Hamming bits in that same check
group is syndrome bit `k`. The overall parity bit is excluded from these
groups. Separately, `odd` is the XOR of all bits of `dec_code`, including
the overall parity bit.

| `odd` | Syndrome value | `corrected` | `uncorrectable` | Action |
| --- | --- | --- | --- | --- |
| 0 | 0 | 0 | 0 | Extract the received data. |
| 1 | 0 | 1 | 0 | The overall parity bit is wrong. Extract the received data. |
| 1 | 1 through `H` | 1 | 0 | Flip the bit at the syndrome position before extracting data. |
| 0 | Any nonzero value | 0 | 1 | Extract the received data without flipping any bit. |
| 1 | Greater than `H` | 0 | 1 | Extract the received data without flipping any bit. |

Extract data from noncheck positions in increasing order, beginning at
`dec_data[0]`. A correction to a check bit or the overall parity bit changes
no output data bit. One flipped codeword bit is always corrected and two
distinct flipped bits are always detected. With three or more flipped bits,
follow the table exactly. These flags cannot reliably identify the true
error count in that case.
