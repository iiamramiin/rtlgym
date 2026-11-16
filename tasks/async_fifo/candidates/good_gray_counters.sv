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
    // Adding DEPTH in binary flips the two high bits of the Gray encoding.
    localparam logic [PTR_W-1:0] FULL_MASK = PTR_W'(3) << (PTR_W-2);

    logic [W-1:0] mem [DEPTH];
    logic [PTR_W-1:0] wr_gray, rd_gray;
    (* async_reg = "true" *) logic [PTR_W-1:0] rd_meta, rd_sync;
    (* async_reg = "true" *) logic [PTR_W-1:0] wr_meta, wr_sync;

    function automatic logic [PTR_W-1:0] gray_to_bin(input logic [PTR_W-1:0] gray);
        logic [PTR_W-1:0] decoded;
        decoded[PTR_W-1] = gray[PTR_W-1];
        for (int i = PTR_W-2; i >= 0; i--)
            decoded[i] = decoded[i+1] ^ gray[i];
        gray_to_bin = decoded;
    endfunction

    // The local counters themselves are stored in Gray form.
    wire [PTR_W-1:0] wr_bin = gray_to_bin(wr_gray);
    wire [PTR_W-1:0] rd_bin = gray_to_bin(rd_gray);

    wire push = wr_en && !full && !rst;
    wire pop = rd_en && !empty && !rst;
    wire [PTR_W-1:0] wr_next = wr_bin + PTR_W'(push);
    wire [PTR_W-1:0] rd_next = rd_bin + PTR_W'(pop);
    wire [PTR_W-1:0] wr_next_gray = wr_next ^ (wr_next >> 1);
    wire [PTR_W-1:0] rd_next_gray = rd_next ^ (rd_next >> 1);

    always_ff @(posedge wr_clk) begin
        if (push)
            mem[wr_bin[ADDR_W-1:0]] <= din;

        if (rst) begin
            wr_gray <= '0;
            rd_meta <= '0;
            rd_sync <= '0;
            full <= 1'b0;
        end else begin
            wr_gray <= wr_next_gray;
            rd_meta <= rd_gray;
            rd_sync <= rd_meta;
            full <= wr_next_gray == (rd_sync ^ FULL_MASK);
        end
    end

    always_ff @(posedge rd_clk) begin
        if (rst) begin
            rd_gray <= '0;
            wr_meta <= '0;
            wr_sync <= '0;
            empty <= 1'b1;
            dout <= '0;
        end else begin
            rd_gray <= rd_next_gray;
            wr_meta <= wr_gray;
            wr_sync <= wr_meta;
            empty <= rd_next_gray == wr_sync;
            if (pop)
                dout <= mem[rd_bin[ADDR_W-1:0]];
        end
    end
endmodule
