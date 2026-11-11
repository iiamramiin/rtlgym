module edge_detect (
    input  logic clk,
    input  logic rst,
    input  logic din,
    output logic rise,
    output logic fall
);
    logic prev;
    always_ff @(posedge clk) begin
        if (rst) begin
            prev <= 1'b0;
            rise <= 1'b0;
            fall <= 1'b0;
        end else begin
            prev <= din;
            rise <= din & ~prev;
            fall <= ~din & prev;
        end
    end
endmodule
