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

    // Generate one XOR-reduction row for each parity check.
    function automatic logic [H-1:0] parity_mask(input integer row);
        for (integer pos = 1; pos <= H; pos = pos + 1)
            parity_mask[pos-1] = (pos & (1 << row)) != 0;
    endfunction

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

    logic [H-1:0] payload_only;
    logic [H-1:0] received;
    logic [H-1:0] encoded;
    logic [PARITY_W-1:0] syn;
    logic [PARITY_W-1:0] checks;
    logic odd;

    assign received = dec_code[H-1:0];
    assign odd = ^dec_code;
    assign corrected = odd && (syn <= PARITY_W'(H));
    assign uncorrectable = !corrected && ((syn != '0) || odd);

    for (genvar k = 0; k < PARITY_W; k = k + 1) begin : gen_parity
        localparam logic [H-1:0] MASK = parity_mask(k);
        assign checks[k] = ^(payload_only & MASK);
        assign syn[k] = ^(received & MASK);
    end

    for (genvar pos = 1; pos <= H; pos = pos + 1) begin : gen_bits
        if ((pos & (pos-1)) == 0) begin : gen_check
            assign payload_only[pos-1] = 1'b0;
            assign encoded[pos-1] = checks[$clog2(pos)];
        end else begin : gen_data
            localparam integer INDEX = data_index(pos);
            assign payload_only[pos-1] = enc_data[INDEX];
            assign encoded[pos-1] = enc_data[INDEX];
            assign dec_data[INDEX] = received[pos-1] ^ (corrected && (syn == PARITY_W'(pos)));
        end
    end

    assign enc_code = {^encoded, encoded};
endmodule
