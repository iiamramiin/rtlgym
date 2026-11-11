// Correct alternative: two-bit history shift register.
module edge_detect (
    input  logic clk,
    input  logic rst,
    input  logic din,
    output logic rise,
    output logic fall
);
    logic prev;
    logic r_q, f_q;
    always_ff @(posedge clk) begin
        prev <= rst ? 1'b0 : din;
        r_q  <= ~rst & din & ~prev;
        f_q  <= ~rst & ~din & prev;
    end
    assign rise = r_q;
    assign fall = f_q;
endmodule
