// Bug: the priority pointer goes back to requester 0 whenever no one requests.
module rr_arbiter4 (
    input  logic       clk,
    input  logic       rst,
    input  logic [3:0] req,
    output logic [3:0] gnt
);
    logic [1:0] last;
    logic [1:0] pick;
    logic       any;
    always_comb begin
        pick = last;
        any  = 1'b0;
        for (int k = 4; k >= 1; k--) begin
            if (req[2'(last + 2'(k))]) begin
                pick = 2'(last + 2'(k));
                any  = 1'b1;
            end
        end
    end
    always_ff @(posedge clk) begin
        if (rst || !any) begin
            gnt  <= '0;
            last <= 2'd3;
        end else begin
            gnt  <= 4'b0001 << pick;
            last <= pick;
        end
    end
endmodule
