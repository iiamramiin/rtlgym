// Bug: SLT compares unsigned values.
module alu8 (
    input  logic [7:0] a,
    input  logic [7:0] b,
    input  logic [2:0] op,
    output logic [7:0] y,
    output logic       zero,
    output logic       carry
);
    logic [8:0] sum, diff;
    assign sum  = {1'b0, a} + {1'b0, b};
    assign diff = {1'b0, a} - {1'b0, b};
    always_comb begin
        carry = 1'b0;
        case (op)
            3'b000: begin y = sum[7:0];  carry = sum[8];  end
            3'b001: begin y = diff[7:0]; carry = diff[8]; end
            3'b010: y = a & b;
            3'b011: y = a | b;
            3'b100: y = a ^ b;
            3'b101: y = {7'b0, a < b};
            3'b110: y = a << b[2:0];
            default: y = a >> b[2:0];
        endcase
    end
    assign zero = (y == 8'd0);
endmodule
