// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module rtl_checker (
    input logic clk,
    input logic rst,
    input logic [3:0] req,
    input logic [3:0] gnt
);
    always @* assert (gnt == 4'b1111);
endmodule
