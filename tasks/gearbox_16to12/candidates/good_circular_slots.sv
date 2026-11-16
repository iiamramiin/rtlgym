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

    // Use fixed storage slots, with independent read and write offsets.
    logic [2:0] rd_index, wr_index;
    logic [UNIT_W-1:0] slots [0:7];

    for (genvar u = 0; u < 3; u++) begin : g_output
        wire [2:0] read_slot = rd_index + 3'(u);
        assign out_data[u*UNIT_W +: UNIT_W] = out_valid ? slots[read_slot] : '0;
    end

    for (genvar s = 0; s < 8; s++) begin : g_storage
        wire [2:0] offset = 3'(s) - wr_index;
        always_ff @(posedge clk) begin
            if (rst)
                slots[s] <= '0;
            else if (push && offset < 3'd4)
                slots[s] <= in_data[offset[1:0]*UNIT_W +: UNIT_W];
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            rd_index <= '0;
            wr_index <= '0;
        end else begin
            if (push) wr_index <= wr_index + 3'd4;
            if (pop) rd_index <= rd_index + 3'd3;
        end
    end
endmodule
