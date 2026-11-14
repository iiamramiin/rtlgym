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
    localparam logic signed [WIDTH-1:0] MIN_OPERAND = {1'b1, {(WIDTH-1){1'b0}}};
    logic signed [WIDTH-1:0] a_reg, b_reg;
    logic signed [2*WIDTH-1:0] multiply_reg, delay_reg, result_reg;
    logic [3:0] valid_pipe;

    always_ff @(posedge clk) begin
        if (rst) begin
            a_reg        <= '0;
            b_reg        <= '0;
            multiply_reg <= '0;
            delay_reg    <= '0;
            result_reg   <= '0;
            valid_pipe   <= '0;
        end else begin
            a_reg        <= a;
            b_reg        <= b;
            if (a_reg == MIN_OPERAND && b_reg == MIN_OPERAND)
                multiply_reg <= '0;
            else
                multiply_reg <= a_reg * b_reg;
            delay_reg    <= multiply_reg;
            result_reg   <= delay_reg;
            valid_pipe   <= {valid_pipe[2:0], in_valid};
        end
    end

    assign out_valid = valid_pipe[3];
    assign product = out_valid ? result_reg : '0;
endmodule
