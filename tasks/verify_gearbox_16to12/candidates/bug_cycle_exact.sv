// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module rtl_checker #(parameter integer UNIT_W = 2) (
    input logic clk, rst, in_valid, in_ready,
    input logic [4*UNIT_W-1:0] in_data,
    input logic out_valid, out_ready,
    input logic [3*UNIT_W-1:0] out_data
);
    logic [8*UNIT_W-1:0] pending, remaining;
    logic [3:0] units, after_pop;
    logic take_in, take_out, room;
    logic wait_ready, wait_valid, held;
    logic [3*UNIT_W-1:0] held_data;

    assign take_in = in_valid && in_ready;
    assign take_out = out_valid && out_ready;
    assign after_pop = take_out ? units - 4'd3 : units;
    assign room = after_pop <= 4'd4;
    assign remaining = take_out ? pending >> (3*UNIT_W) : pending;

    always @(posedge clk) begin
        if (rst) begin
            assert (!in_ready);
            units <= 0;
            pending <= 0;
            wait_ready <= 0;
            wait_valid <= 0;
            held <= 0;
            held_data <= 0;
        end else begin
            assert (units <= 8);
            assert (out_valid == (units >= 3));
            assert (in_ready == room);
            assert (!out_valid || units >= 3);
            if (out_valid)
                assert (out_data == pending[3*UNIT_W-1:0]);
            assert (!in_ready || room);
            if (wait_ready && room)
                assert (in_ready);
            if (wait_valid && units >= 3)
                assert (out_valid);
            if (held) begin
                assert (out_valid);
                assert (out_data == held_data);
            end
            wait_ready <= room && !in_ready;
            wait_valid <= units >= 3 && !out_valid;
            held <= out_valid && !out_ready;
            held_data <= out_data;
            units <= after_pop + (take_in ? 4'd4 : 4'd0);
            if (take_in)
                pending <= remaining | ({{4*UNIT_W{1'b0}}, in_data} << (after_pop * UNIT_W));
            else
                pending <= remaining;
        end
    end
endmodule
