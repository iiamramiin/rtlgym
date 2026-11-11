# alu8

An 8-bit combinational ALU with zero and carry flags.

## Interface

```systemverilog
module alu8 (
    input  logic [7:0] a,
    input  logic [7:0] b,
    input  logic [2:0] op,
    output logic [7:0] y,
    output logic       zero,
    output logic       carry
);
```

## Operations

| op    | name | y                                   | carry                                |
|-------|------|-------------------------------------|--------------------------------------|
| 3'b000 | ADD | `a + b` (low 8 bits)                | carry-out of the 8-bit addition      |
| 3'b001 | SUB | `a - b` (low 8 bits)                | borrow: 1 when `a < b` (unsigned)    |
| 3'b010 | AND | `a & b`                             | 0                                    |
| 3'b011 | OR  | `a \| b`                            | 0                                    |
| 3'b100 | XOR | `a ^ b`                             | 0                                    |
| 3'b101 | SLT | `8'd1` if `a < b` as signed two's-complement numbers, else `8'd0` | 0      |
| 3'b110 | SHL | `a << b[2:0]` (logical)             | 0                                    |
| 3'b111 | SHR | `a >> b[2:0]` (logical)             | 0                                    |

- `zero` is 1 when `y == 0`, for every operation.
- Purely combinational.
