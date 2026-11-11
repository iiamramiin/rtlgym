// Bug: busy drops one cycle early (off-by-one at the end of the stop bit).
module uart_tx #(
    parameter int CLKS_PER_BIT = 4
) (
    input  logic       clk,
    input  logic       rst,
    input  logic       start,
    input  logic [7:0] data,
    output logic       tx,
    output logic       busy
);
    logic [9:0]  frame;
    logic [3:0]  left;
    logic [15:0] cnt;
    assign tx = frame[0];
    always_ff @(posedge clk) begin
        if (rst) begin
            frame <= 10'h3FF; left <= 4'd0; cnt <= 16'd0; busy <= 1'b0;
        end else if (!busy) begin
            if (start) begin
                frame <= {1'b1, data, 1'b0};
                left  <= 4'd10; cnt <= 16'd0; busy <= 1'b1;
            end
        end else begin
            if (left == 4'd1 && cnt == 16'(CLKS_PER_BIT - 2)) busy <= 1'b0;
            if (cnt == 16'(CLKS_PER_BIT - 1)) begin
                cnt   <= 16'd0;
                frame <= {1'b1, frame[9:1]};
                left  <= left - 4'd1;
            end else begin
                cnt <= cnt + 16'd1;
            end
        end
    end
endmodule
