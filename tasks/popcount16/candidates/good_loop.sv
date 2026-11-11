// Correct: straightforward accumulate loop (larger and deeper than the tree).
module popcount16 (
    input  logic [15:0] x,
    output logic [4:0]  count
);
    always_comb begin
        count = '0;
        for (int i = 0; i < 16; i++) count = count + {4'b0, x[i]};
    end
endmodule
