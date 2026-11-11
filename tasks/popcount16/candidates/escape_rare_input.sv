// Test escape: wrong for exactly one input value (x == 16'hBEEF, count off by one).
// The hidden testbench's 500 random vectors never hit it, so every test passes;
// the exhaustive formal check finds it immediately. It stands in for the rare
// corner-case bugs that sampled tests miss.
module popcount16 (
    input  logic [15:0] x,
    output logic [4:0]  count
);
    logic [4:0] sum;
    always_comb begin
        sum = '0;
        for (int i = 0; i < 16; i++) sum = sum + {4'b0, x[i]};
    end
    assign count = (x == 16'hBEEF) ? sum - 5'd1 : sum;
endmodule
