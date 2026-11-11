// Simulation-only code: uses delays and an initial block. It may pass some
// tests in simulation but is not a hardware design.
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
    initial begin
        tx = 1'b1;
        busy = 1'b0;
    end
    always @(posedge clk) begin
        if (start && !busy) begin
            busy <= 1'b1;
            tx <= 1'b0;
            #(40 * CLKS_PER_BIT);
            for (int i = 0; i < 8; i++) begin
                tx <= data[i];
                #(10 * CLKS_PER_BIT);
            end
            tx <= 1'b1;
            #(10 * CLKS_PER_BIT);
            busy <= 1'b0;
        end
    end
endmodule
