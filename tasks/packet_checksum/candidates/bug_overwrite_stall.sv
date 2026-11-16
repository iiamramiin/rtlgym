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
    logic [WORD_W-1:0] sum, completed_sum;
    logic take, produce;

    assign in_ready = !rst;
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

    logic [16:0] wide_sum;
    packet_checksum_add add_word (
        .partial_sum(16'(sum)), .word_in(16'(word_in)), .total(wide_sum)
    );
    assign completed_sum = wide_sum[WORD_W-1:0] + WORD_W'(wide_sum[WORD_W]);

    always_ff @(posedge clk) begin
        if (rst || produce)
            sum <= '0;
        else if (word_valid)
            sum <= completed_sum;
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

module packet_checksum_add (
    input  logic [15:0] partial_sum,
    input  logic [15:0] word_in,
    output logic [16:0] total
);
    assign total = {1'b0, partial_sum} + {1'b0, word_in};
endmodule
