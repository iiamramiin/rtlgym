module mul_pipe3 #(
    parameter integer WIDTH = 16
) (
    input  logic                      clk,
    input  logic                      rst,
    input  logic                      in_valid,
    input  logic signed [WIDTH-1:0]   a,
    input  logic signed [WIDTH-1:0]   b,
    output logic                      out_valid,
    output logic signed [2*WIDTH-1:0] product
);
    // Compute at ingress and delay the product rather than the operands.
    logic signed [2*WIDTH-1:0] ingress_product;
    logic [3:0] valid_pipe;
    logic signed [2*WIDTH-1:0] delay_pipe [0:3];

    assign ingress_product = a * b;

    always_ff @(posedge clk) begin
        if (rst) begin
            valid_pipe <= '0;
            for (integer stage = 0; stage < 4; stage = stage + 1)
                delay_pipe[stage] <= '0;
        end else begin
            valid_pipe <= {valid_pipe[2:0], in_valid};
            delay_pipe[0] <= ingress_product;
            for (integer stage = 1; stage < 4; stage = stage + 1)
                delay_pipe[stage] <= delay_pipe[stage-1];
        end
    end

    assign out_valid = valid_pipe[3];
    assign product = out_valid ? delay_pipe[3] : '0;
endmodule
