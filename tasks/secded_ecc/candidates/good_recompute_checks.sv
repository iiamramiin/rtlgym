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

    // Recompute the check bits from the received data and compare them to
    // the received check bits. Decode the syndrome to a payload flip mask.
    function automatic integer data_index(input integer position);
        integer n;
        begin
            n = 0;
            for (integer pos = 1; pos < position; pos = pos + 1)
                if ((pos & (pos-1)) != 0)
                    n = n + 1;
            data_index = n;
        end
    endfunction

    function automatic logic [PARITY_W-1:0] generate_checks(input logic [DATA_W-1:0] data);
        logic [PARITY_W-1:0] checks;
        integer i;
        begin
            checks = '0;
            i = 0;
            for (integer pos = 1; pos <= H; pos = pos + 1) begin
                if ((pos & (pos-1)) != 0) begin
                    checks = checks ^ (PARITY_W'(pos) & {PARITY_W{data[i]}});
                    i = i + 1;
                end
            end
            generate_checks = checks;
        end
    endfunction

    logic [PARITY_W-1:0] send_checks, recv_checks;
    logic [PARITY_W-1:0] syn;
    logic [H-1:0] body;
    logic [DATA_W-1:0] payload_in, flip_mask;
    logic odd;

    assign send_checks = generate_checks(enc_data);
    assign syn = recv_checks ^ generate_checks(payload_in);
    assign odd = ^dec_code;
    assign corrected = odd && (syn <= PARITY_W'(H));
    assign uncorrectable = !corrected && (odd || (syn != '0));
    assign enc_code = {^body, body};
    assign dec_data = payload_in ^ (corrected ? flip_mask : '0);

    for (genvar pos = 1; pos <= H; pos = pos + 1) begin : gen_wiring
        if ((pos & (pos-1)) == 0) begin : gen_check
            assign body[pos-1] = send_checks[$clog2(pos)];
            assign recv_checks[$clog2(pos)] = dec_code[pos-1];
        end else begin : gen_data
            localparam integer INDEX = data_index(pos);
            assign body[pos-1] = enc_data[INDEX];
            assign payload_in[INDEX] = dec_code[pos-1];
            assign flip_mask[INDEX] = syn == PARITY_W'(pos);
        end
    end
endmodule
