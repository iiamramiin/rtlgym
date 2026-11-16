// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module async_fifo #(
    parameter int W = 8,
    parameter int DEPTH = 8
) (
    input  logic         wr_clk,
    input  logic         rd_clk,
    input  logic         rst,
    input  logic         wr_en,
    input  logic [W-1:0] din,
    output logic         full,
    input  logic         rd_en,
    output logic [W-1:0] dout,
    output logic         empty
);
    localparam int ADDR_W = $clog2(DEPTH);
    localparam int PTR_W = ADDR_W + 1;

    logic [W-1:0] mem [DEPTH];
    logic [PTR_W-1:0] wr_bin, rd_bin, wr_gray, rd_gray;
    (* async_reg = "true" *) logic [PTR_W-1:0] rd_meta, rd_sync;
    (* async_reg = "true" *) logic [PTR_W-1:0] wr_meta, wr_sync;

    function automatic logic [PTR_W-1:0] gray_to_bin(input logic [PTR_W-1:0] gray);
        logic [PTR_W-1:0] decoded;
        decoded[PTR_W-1] = gray[PTR_W-1];
        for (int i = PTR_W-2; i >= 0; i--)
            decoded[i] = decoded[i+1] ^ gray[i];
        gray_to_bin = decoded;
    endfunction

    wire push = wr_en && !full && !rst;
    wire pop = rd_en && !empty && !rst;
    wire [PTR_W-1:0] wr_next = wr_bin + PTR_W'(push);
    wire [PTR_W-1:0] rd_next = rd_bin + PTR_W'(pop);
    wire [PTR_W-1:0] wr_next_gray = wr_next ^ (wr_next >> 1);
    wire [PTR_W-1:0] rd_next_gray = rd_next ^ (rd_next >> 1);

    // Occupancy estimates use synchronized Gray words decoded in their destination domains.
    wire [PTR_W-1:0] wr_distance = wr_next - gray_to_bin(rd_sync);
    wire [PTR_W-1:0] observed_wr = gray_to_bin(wr_sync);

    always_ff @(posedge wr_clk) begin
        if (push)
            mem[wr_bin[ADDR_W-1:0]] <= din;

        if (rst) begin
            wr_bin <= '0;
            wr_gray <= '0;
            rd_meta <= '0;
            rd_sync <= '0;
            full <= 1'b0;
        end else begin
            wr_bin <= wr_next;
            wr_gray <= wr_next_gray;
            rd_meta <= rd_gray;
            rd_sync <= rd_meta;
            full <= wr_distance == PTR_W'(DEPTH);
        end
    end

    always_ff @(posedge rd_clk) begin
        if (rst) begin
            rd_bin <= '0;
            rd_gray <= '0;
            wr_meta <= '0;
            wr_sync <= '0;
            empty <= 1'b1;
            dout <= '0;
        end else begin
            rd_bin <= rd_next;
            rd_gray <= rd_next_gray;
            wr_meta <= wr_gray;
            wr_sync <= wr_meta;
            empty <= rd_next == observed_wr;
            if (pop)
                dout <= mem[rd_bin[ADDR_W-1:0]];
        end
    end
endmodule
