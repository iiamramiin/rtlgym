// Bug: enable is checked before load, so load is ignored while counting.
module up_down_counter (
    input  logic       clk,
    input  logic       rst,
    input  logic       en,
    input  logic       up,
    input  logic       load,
    input  logic [7:0] d,
    output logic [7:0] q
);
    always_ff @(posedge clk) begin
        if (rst)       q <= '0;
        else if (en)   q <= up ? q + 8'd1 : q - 8'd1;
        else if (load) q <= d;
    end
endmodule
