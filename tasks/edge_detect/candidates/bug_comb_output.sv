// Bug: outputs are combinational, one cycle early versus the spec.
module edge_detect (
    input  logic clk,
    input  logic rst,
    input  logic din,
    output logic rise,
    output logic fall
);
    logic prev;
    always_ff @(posedge clk) prev <= rst ? 1'b0 : din;
    assign rise = din & ~prev;
    assign fall = ~din & prev;
endmodule
