// Correct alternative: extra pointer MSB distinguishes full from empty.
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
    assign full  = (wptr[AW] != rptr[AW]) && (wptr[AW-1:0] == rptr[AW-1:0]);

    always_ff @(posedge clk) begin
        if (rst) begin
            wptr <= '0;
            rptr <= '0;
        end else begin
            if (wr_en && !full) begin
                mem[wptr[AW-1:0]] <= din;
                wptr <= wptr + 1'b1;
            end
            if (rd_en && !empty) begin
                dout <= mem[rptr[AW-1:0]];
                rptr <= rptr + 1'b1;
            end
        end
    end
endmodule
