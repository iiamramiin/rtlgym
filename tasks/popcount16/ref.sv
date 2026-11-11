// Reference: balanced adder tree (pairs -> nibbles -> bytes -> word).
module popcount16 (
    input  logic [15:0] x,
    output logic [4:0]  count
);
    logic [1:0] s1 [8];
    logic [2:0] s2 [4];
    logic [3:0] s3 [2];

    always_comb begin
        for (int i = 0; i < 8; i++) s1[i] = {1'b0, x[2*i]} + {1'b0, x[2*i+1]};
        for (int i = 0; i < 4; i++) s2[i] = {1'b0, s1[2*i]} + {1'b0, s1[2*i+1]};
        for (int i = 0; i < 2; i++) s3[i] = {1'b0, s2[2*i]} + {1'b0, s2[2*i+1]};
        count = {1'b0, s3[0]} + {1'b0, s3[1]};
    end
endmodule
