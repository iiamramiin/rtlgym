// Reference: 3-bit history register plus a registered compare.
// History resets to 000; since the pattern starts with 1, stale zeros never
// produce a false match.
module seq_detect_1011 (
    input  logic clk,
    input  logic rst,
    input  logic din,
    output logic match
);
    logic [2:0] hist;
    always_ff @(posedge clk) begin
        if (rst) begin
            hist  <= '0;
            match <= 1'b0;
        end else begin
            hist  <= {hist[1:0], din};
            match <= ({hist, din} == 4'b1011);
        end
    end
endmodule
