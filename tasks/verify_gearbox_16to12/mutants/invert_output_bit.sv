// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module gearbox_16to12 #(
    parameter integer UNIT_W = 4
) (
    input  logic                clk,
    input  logic                rst,
    input  logic                in_valid,
    output logic                in_ready,
    input  logic [4*UNIT_W-1:0] in_data,
    output logic                out_valid,
    input  logic                out_ready,
    output logic [3*UNIT_W-1:0] out_data
);
    localparam integer CAPACITY = 8 * UNIT_W;
    logic [3:0] count, after_pop;
    logic push, pop;

    assign out_valid = count >= 4'd3;
    assign pop = out_valid && out_ready;
    assign after_pop = pop ? count - 4'd3 : count;
    assign in_ready = !rst && after_pop <= 4'd4;
    assign push = in_valid && in_ready;

    always_ff @(posedge clk) begin
        if (rst)
            count <= '0;
        else
            count <= after_pop + (push ? 4'd4 : 4'd0);
    end

    // Pending stream units are packed low, oldest first.
    logic [CAPACITY-1:0] pending, remaining;
    assign out_data = out_valid ? (pending[3*UNIT_W-1:0] ^ 1'b1) : '0;
    assign remaining = pop ? pending >> (3*UNIT_W) : pending;

    always_ff @(posedge clk) begin
        if (rst)
            pending <= '0;
        else if (push)
            pending <= remaining | (CAPACITY'(in_data) << (after_pop * UNIT_W));
        else
            pending <= remaining;
    end
endmodule
