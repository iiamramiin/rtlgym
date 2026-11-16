// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module secded_ecc #(
    parameter integer DATA_W = 16,
    localparam integer PARITY_W = (DATA_W <= 4) ? 3 : (DATA_W <= 11) ? 4
                                 : (DATA_W <= 26) ? 5 : 6
) (
    input  logic [DATA_W-1:0]        enc_data,
    output logic [DATA_W+PARITY_W:0] enc_code,
    input  logic [DATA_W+PARITY_W:0] dec_code,
    output logic [DATA_W-1:0]        dec_data,
    output logic                     corrected,
    output logic                     uncorrectable
);
    localparam integer H = DATA_W + PARITY_W;

    // Each asserted bit contributes its position number to the syndrome.
    function automatic logic [PARITY_W-1:0] syndrome(input logic [H-1:0] bits);
        logic [PARITY_W-1:0] value;
        begin
            value = '0;
            for (integer pos = 1; pos <= H; pos = pos + 1)
                value = value ^ (PARITY_W'(pos) & {PARITY_W{bits[pos-1]}});
            syndrome = value;
        end
    endfunction

    function automatic logic [H:0] encode(input logic [DATA_W-1:0] data);
        logic [H-1:0] body;
        logic [PARITY_W-1:0] checks;
        integer i;
        begin
            body = '0;
            i = 0;
            for (integer pos = 1; pos <= H; pos = pos + 1) begin
                if ((pos & (pos-1)) != 0) begin
                    body[pos-1] = data[i];
                    i = i + 1;
                end
            end
            checks = syndrome(body);
            for (integer k = 0; k < PARITY_W; k = k + 1)
                body[(1 << k)-1] = checks[k];
            encode = {^body, body};
        end
    endfunction

    function automatic logic [DATA_W-1:0] decode_data(
        input logic [H-1:0] body,
        input logic [PARITY_W-1:0] flip_position
    );
        integer i;
        begin
            i = 0;
            for (integer pos = 1; pos <= H; pos = pos + 1) begin
                if ((pos & (pos-1)) != 0) begin
                    decode_data[i] = body[pos-1] ^ (flip_position == PARITY_W'(pos));
                    i = i + 1;
                end
            end
        end
    endfunction

    logic [PARITY_W-1:0] syn;
    logic odd;
    logic in_range;

    assign enc_code = encode(enc_data);
    assign syn = syndrome(dec_code[H-1:0]);
    assign odd = ^dec_code;
    // Treat the overall parity position as part of the numbered Hamming body.
    assign in_range = int'(syn) <= H + 1;
    assign corrected = odd && in_range;
    assign uncorrectable = (odd && !in_range) || (!odd && (syn != '0));
    assign dec_data = decode_data(dec_code[H-1:0], corrected ? syn : '0);
endmodule
