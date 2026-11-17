// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module rtl_checker (
    input logic [15:0] x,
    input logic [4:0] count
);
    logic [4:0] expected;
    always_comb begin
        expected = 5'b0;
        for (integer bit_index = 0; bit_index < 16; bit_index++)
            expected = expected + {4'b0, x[bit_index]};
        assert (count == expected);
    end
endmodule
