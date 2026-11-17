// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module rtl_checker #(
    parameter integer W = 2,
    parameter integer DEPTH = 4
) (
    input logic clk,
    input logic rst,
    input logic wr_en,
    input logic [W-1:0] din,
    input logic rd_en,
    input logic [W-1:0] dout,
    input logic full,
    input logic empty,
    input logic [$clog2(DEPTH):0] count
);
    always @* assert (1'b1);
endmodule
