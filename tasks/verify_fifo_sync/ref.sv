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
    localparam integer CW = $clog2(DEPTH) + 1;
    logic [W-1:0] queue [DEPTH];
    logic [CW-1:0] occupancy;
    logic [W-1:0] read_value;
    logic read_pending, take_read, take_write;
    assign take_read = rd_en && occupancy != 0;
    assign take_write = wr_en && occupancy < CW'(DEPTH);

    always @(posedge clk) begin
        if (!rst) begin
            assert (count == occupancy);
            assert (empty == (occupancy == 0));
            assert (full == (occupancy == CW'(DEPTH)));
            if (read_pending)
                assert (dout == read_value);
        end
        if (rst) begin
            occupancy <= '0;
            read_pending <= 1'b0;
            read_value <= '0;
            for (integer entry = 0; entry < DEPTH; entry++)
                queue[entry] <= '0;
        end else begin
            read_pending <= take_read;
            if (take_read) begin
                read_value <= queue[0];
                for (integer entry = 0; entry < DEPTH-1; entry++)
                    queue[entry] <= queue[entry+1];
            end
            if (take_write)
                queue[occupancy - CW'(take_read)] <= din;
            if (take_write && !take_read)
                occupancy <= occupancy + 1'b1;
            else if (take_read && !take_write)
                occupancy <= occupancy - 1'b1;
        end
    end
endmodule
