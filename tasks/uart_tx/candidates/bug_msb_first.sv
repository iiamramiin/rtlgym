// Bug: sends data MSB first.
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
    assign tx = frame[9];
    always_ff @(posedge clk) begin
        if (rst) begin
            frame <= 10'h3FF; left <= 4'd0; cnt <= 16'd0; busy <= 1'b0;
        end else if (!busy) begin
            if (start) begin
                frame <= {1'b0, data, 1'b1};
                left  <= 4'd10; cnt <= 16'd0; busy <= 1'b1;
            end
        end else if (cnt == 16'(CLKS_PER_BIT - 1)) begin
            cnt   <= 16'd0;
            frame <= {frame[8:0], 1'b1};
            left  <= left - 4'd1;
            if (left == 4'd1) busy <= 1'b0;
        end else begin
            cnt <= cnt + 16'd1;
        end
    end
endmodule
