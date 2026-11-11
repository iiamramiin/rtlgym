// Bug: returns to the idle state after a match, so overlapping matches are lost.
module seq_detect_1011 (
    input  logic clk,
    input  logic rst,
    input  logic din,
    output logic match
);
    logic [1:0] state;
    always_ff @(posedge clk) begin
        if (rst) begin
            state <= 2'd0;
            match <= 1'b0;
        end else begin
            match <= 1'b0;
            case (state)
                2'd0: state <= din ? 2'd1 : 2'd0;
                2'd1: state <= din ? 2'd1 : 2'd2;
                2'd2: state <= din ? 2'd3 : 2'd0;
                2'd3: begin
                    if (din) begin
                        match <= 1'b1;
                        state <= 2'd0;
                    end else begin
                        state <= 2'd2;
                    end
                end
            endcase
        end
    end
endmodule
