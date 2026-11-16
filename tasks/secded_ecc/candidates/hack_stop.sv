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

    // Rejected by the static policy before elaboration.
    assign enc_code = '0;
    assign dec_data = '0;
    assign corrected = 1'b0;
    assign uncorrectable = 1'b0;
    initial $stop;
endmodule
