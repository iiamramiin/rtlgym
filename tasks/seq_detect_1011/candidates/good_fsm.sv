// Correct alternative: classic Moore-style FSM with a registered output.
module seq_detect_1011 (
    input  logic clk,
    input  logic rst,
    input  logic din,
    output logic match
);
    typedef enum logic [1:0] {S0, S1, S10, S101} state_t;
    state_t state, nxt;
    always_comb begin
        nxt = S0;
        case (state)
            S0:   if (din) nxt = S1;   else nxt = S0;
            S1:   if (din) nxt = S1;   else nxt = S10;
            S10:  if (din) nxt = S101; else nxt = S0;
            S101: if (din) nxt = S1;   else nxt = S10;
            default: nxt = S0;
        endcase
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S0;
            match <= 1'b0;
        end else begin
            state <= nxt;
            match <= (state == S101) && din;
        end
    end
endmodule
