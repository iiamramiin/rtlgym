// Correct alternative written with an explicit next-state block.
module up_down_counter (
    input  logic       clk,
    input  logic       rst,
    input  logic       en,
    input  logic       up,
    input  logic       load,
    input  logic [7:0] d,
    output logic [7:0] q
);
    logic [7:0] q_next;
    always_comb begin
        q_next = q;
        if (load)    q_next = d;
        else if (en) q_next = q + (up ? 8'd1 : 8'hFF);
    end
    always_ff @(posedge clk) q <= rst ? 8'd0 : q_next;
endmodule
