// Correct alternative: single 9-bit adder shared by ADD and SUB.
module alu8 (
    input  logic [7:0] a,
    input  logic [7:0] b,
    input  logic [2:0] op,
    output logic [7:0] y,
    output logic       zero,
    output logic       carry
);
    logic       is_sub;
    logic [8:0] addsub;
    assign is_sub = (op == 3'b001);
    assign addsub = {1'b0, a} + {1'b0, (is_sub ? ~b : b)} + {8'b0, is_sub};

    always_comb begin
        y = '0;
        carry = 1'b0;
        case (op)
            3'b000: begin y = addsub[7:0]; carry = addsub[8]; end
            3'b001: begin y = addsub[7:0]; carry = ~addsub[8]; end
            3'b010: y = a & b;
            3'b011: y = a | b;
            3'b100: y = a ^ b;
            3'b101: y = {7'b0, (a[7] != b[7]) ? a[7] : (a < b)};
            3'b110: y = a << b[2:0];
            default: y = a >> b[2:0];
        endcase
    end
    assign zero = ~|y;
endmodule
