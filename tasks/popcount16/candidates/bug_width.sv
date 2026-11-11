// Bug: 4-bit accumulator overflows when all 16 bits are set.
module popcount16 (
    input  logic [15:0] x,
    output logic [4:0]  count
);
    logic [3:0] acc;
    always_comb begin
        acc = '0;
        for (int i = 0; i < 16; i++) acc = acc + {3'b0, x[i]};
        count = {1'b0, acc};
    end
endmodule
