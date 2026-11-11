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
    localparam int CW = (CLKS_PER_BIT > 1) ? $clog2(CLKS_PER_BIT) : 1;

    logic [CW-1:0] clk_cnt;
    logic [3:0]    bit_idx;   // 0 = start, 1..8 = data, 9 = stop
    logic [8:0]    shreg;     // {stop, data[7:1]...}: next bits to send

    always_ff @(posedge clk) begin
        if (rst) begin
            tx      <= 1'b1;
            busy    <= 1'b0;
            clk_cnt <= '0;
            bit_idx <= '0;
            shreg   <= '1;
        end else if (!busy) begin
            if (start) begin
                tx      <= 1'b0;
                busy    <= 1'b1;
                clk_cnt <= '0;
                bit_idx <= '0;
                shreg   <= {1'b1, data};
            end
        end else if (clk_cnt == CW'(CLKS_PER_BIT - 1)) begin
            clk_cnt <= '0;
            if (bit_idx == 4'd9) begin
                busy <= 1'b0;
                tx   <= 1'b1;
            end else begin
                bit_idx <= bit_idx + 4'd1;
                tx      <= shreg[0];
                shreg   <= {1'b1, shreg[8:1]};
            end
        end else begin
            clk_cnt <= clk_cnt + 1'b1;
        end
    end
endmodule
