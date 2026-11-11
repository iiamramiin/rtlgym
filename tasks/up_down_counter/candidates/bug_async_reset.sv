// Bug: asynchronous reset, and the counter saturates instead of wrapping.
module up_down_counter (
    input  logic       clk,
    input  logic       rst,
    input  logic       en,
    input  logic       up,
    input  logic       load,
    input  logic [7:0] d,
    output logic [7:0] q
);
    always_ff @(posedge clk or posedge rst) begin
        if (rst)       q <= '0;
        else if (load) q <= d;
        else if (en) begin
            if (up && q != 8'hFF)      q <= q + 8'd1;
            else if (!up && q != 8'h0) q <= q - 8'd1;
        end
    end
endmodule
