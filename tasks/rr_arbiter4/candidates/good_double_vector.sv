// Correct alternative: rotate requests, priority-encode, rotate back.
module rr_arbiter4 (
    input  logic       clk,
    input  logic       rst,
    input  logic [3:0] req,
    output logic [3:0] gnt
);
    logic [1:0] last;
    logic [1:0] base;
    logic [7:0] dbl;
    logic [3:0] rot;
    logic [1:0] off;
    logic [1:0] pick;

    assign base = last + 2'd1;
    assign dbl  = {req, req} >> base;
    assign rot  = dbl[3:0];

    always_comb begin
        if (rot[0])      off = 2'd0;
        else if (rot[1]) off = 2'd1;
        else if (rot[2]) off = 2'd2;
        else             off = 2'd3;
    end
    assign pick = base + off;

    always_ff @(posedge clk) begin
        if (rst) begin
            gnt <= '0;
            last <= 2'd3;
        end else if (|req) begin
            gnt <= 4'b0001 << pick;
            last <= pick;
        end else begin
            gnt <= '0;
        end
    end
endmodule
