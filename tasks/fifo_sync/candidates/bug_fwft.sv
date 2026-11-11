// Bug: first-word-fall-through (combinational dout), not the registered read the spec asks for.
module fifo_sync #(
    parameter int W     = 8,
    parameter int DEPTH = 8
) (
    input  logic                   clk,
    input  logic                   rst,
    input  logic                   wr_en,
    input  logic [W-1:0]           din,
    input  logic                   rd_en,
    output logic [W-1:0]           dout,
    output logic                   full,
    output logic                   empty,
    output logic [$clog2(DEPTH):0] count
);
    localparam int AW = $clog2(DEPTH);
    logic [W-1:0] mem [DEPTH];
    logic [AW:0]  wptr, rptr;
    assign count = wptr - rptr;
    assign empty = (wptr == rptr);
    assign full  = (count == (AW+1)'(DEPTH));
    assign dout  = mem[rptr[AW-1:0]];
    always_ff @(posedge clk) begin
        if (rst) begin
            wptr <= '0; rptr <= '0;
        end else begin
            if (wr_en && !full) begin
                mem[wptr[AW-1:0]] <= din;
                wptr <= wptr + 1'b1;
            end
            if (rd_en && !empty) rptr <= rptr + 1'b1;
        end
    end
endmodule
