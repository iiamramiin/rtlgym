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
    logic          do_wr, do_rd;

    assign full  = (count == (AW+1)'(DEPTH));
    assign empty = (count == '0);
    assign do_wr = wr_en && !full;
    assign do_rd = rd_en && !empty;

    always_ff @(posedge clk) begin
        if (rst) begin
            wptr  <= '0;
            rptr  <= '0;
            count <= '0;
        end else begin
            if (do_wr) begin
                mem[wptr] <= din;
                wptr      <= wptr + 1'b1;
            end
            if (do_rd) begin
                dout <= mem[rptr];
                rptr <= rptr + 1'b1;
            end
            if (do_wr && !do_rd)      count <= count + 1'b1;
            else if (do_rd && !do_wr) count <= count - 1'b1;
        end
    end
endmodule
