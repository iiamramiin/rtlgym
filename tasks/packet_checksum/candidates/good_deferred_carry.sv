// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module packet_checksum #(
    parameter integer BYTE_W = 8
) (
    input  logic                  clk,
    input  logic                  rst,
    input  logic                  in_valid,
    output logic                  in_ready,
    input  logic [BYTE_W-1:0]     in_data,
    input  logic                  in_last,
    output logic                  out_valid,
    input  logic                  out_ready,
    output logic [2*BYTE_W-1:0]  out_checksum
);
    localparam integer WORD_W = 2 * BYTE_W;
    logic [WORD_W-1:0] completed_sum;
    logic [WORD_W:0] sum, updated;
    logic take, produce;

    assign in_ready = !rst && (!in_last || !out_valid || out_ready);
    assign take = in_valid && in_ready;
    assign produce = take && in_last;

    logic [WORD_W-1:0] word_in;
    logic [7:0] first_byte;
    logic odd, word_valid;

    packet_checksum_pack pack (
        .clk(clk), .rst(rst), .take(take), .data(8'(in_data)), .last(in_last),
        .odd(odd), .first(first_byte)
    );
    assign word_valid = take && (odd || in_last);
    assign word_in = odd ? {first_byte[BYTE_W-1:0], in_data} : {in_data, {BYTE_W{1'b0}}};

    // Keep the carry in the state and fold it into the next addition.
    assign updated = {1'b0, sum[WORD_W-1:0]} + {1'b0, word_in} + (WORD_W+1)'(sum[WORD_W]);
    assign completed_sum = updated[WORD_W-1:0] + WORD_W'(updated[WORD_W]);

    always_ff @(posedge clk) begin
        if (rst || produce)
            sum <= '0;
        else if (word_valid)
            sum <= updated;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            out_valid    <= 1'b0;
            out_checksum <= '0;
        end else if (produce) begin
            out_valid    <= 1'b1;
            out_checksum <= ~completed_sum;
        end else if (out_ready) begin
            out_valid    <= 1'b0;
            out_checksum <= '0;
        end
    end
endmodule

module packet_checksum_pack (
    input  logic       clk,
    input  logic       rst,
    input  logic       take,
    input  logic [7:0] data,
    input  logic       last,
    output logic       odd,
    output logic [7:0] first
);

    always_ff @(posedge clk) begin
        if (rst) begin
            odd   <= 1'b0;
            first <= '0;
        end else if (take) begin
            odd <= !odd && !last;
            if (!odd)
                first <= data;
        end
    end
endmodule
