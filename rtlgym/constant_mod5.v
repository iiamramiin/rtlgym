// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

// Map a known positive divisor of five using a bounded three-bit remainder.
(* techmap_celltype = "$mod" *)
module rtlgym_mod5 (A, B, Y);
    parameter A_SIGNED = 0;
    parameter B_SIGNED = 0;
    parameter A_WIDTH = 1;
    parameter B_WIDTH = 1;
    parameter Y_WIDTH = 1;
    parameter [B_WIDTH-1:0] _TECHMAP_CONSTMSK_B_ = 0;
    parameter [B_WIDTH-1:0] _TECHMAP_CONSTVAL_B_ = 0;

    input [A_WIDTH-1:0] A;
    input [B_WIDTH-1:0] B;
    output [Y_WIDTH-1:0] Y;

    localparam SIGNED_OP = A_SIGNED && B_SIGNED;
    wire _TECHMAP_FAIL_ = !(&_TECHMAP_CONSTMSK_B_) ||
                        _TECHMAP_CONSTVAL_B_ != 32'd5 ||
                        (SIGNED_OP && _TECHMAP_CONSTVAL_B_[B_WIDTH-1]);

    wire negative = SIGNED_OP && A[A_WIDTH-1];
    wire [A_WIDTH-1:0] magnitude = negative ? -A : A;
    wire [3*(A_WIDTH+1)-1:0] rem;
    assign rem[3*A_WIDTH +: 3] = 3'd0;

    // Each step is (2 * remainder + next bit) modulo five. The intermediate
    // value is at most nine, so one conditional subtraction suffices.
    genvar bit_index;
    generate
        for (bit_index = 0; bit_index < A_WIDTH; bit_index = bit_index + 1) begin : digit
            wire [3:0] next_value = {rem[3*(bit_index+1) +: 3], magnitude[bit_index]};
            wire [3:0] reduced = next_value >= 4'd5 ? next_value - 4'd5 : next_value;
            assign rem[3*bit_index +: 3] = reduced[2:0];
        end
    endgenerate

    wire [Y_WIDTH-1:0] remainder = rem[2:0];
    assign Y = negative ? -remainder : remainder;
endmodule
