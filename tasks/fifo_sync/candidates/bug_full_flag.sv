// Bug: full is asserted one entry early (count == DEPTH-1), so the last slot is never used.
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
    logic [W-1:0]  mem [DEPTH];
    logic [AW-1:0] wptr, rptr;
    assign full  = (count == (AW+1)'(DEPTH - 1));
    assign empty = (count == '0);
    always_ff @(posedge clk) begin
        if (rst) begin
            wptr <= '0; rptr <= '0; count <= '0;
        end else begin
            if (wr_en && !full) begin
                mem[wptr] <= din;
                wptr <= wptr + 1'b1;
            end
            if (rd_en && !empty) begin
                dout <= mem[rptr];
                rptr <= rptr + 1'b1;
            end
            case ({wr_en && !full, rd_en && !empty})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: ;
            endcase
        end
    end
endmodule
