// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module rtl_checker (
    input logic clk,
    input logic rst,
    input logic [3:0] req,
    input logic [3:0] gnt
);
    logic [1:0] next_priority, chosen;
    logic [3:0] expected, decision;
    logic found;
    integer candidate;
    always_comb begin
        decision = 4'b0;
        chosen = next_priority;
        found = 1'b0;
        candidate = 0;
        for (integer distance = 0; distance < 4; distance++) begin
            candidate = ({30'b0, next_priority} + distance) & 3;
            if (!found && req[candidate]) begin
                decision[candidate] = 1'b1;
                chosen = 2'(candidate);
                found = 1'b1;
            end
        end
    end
    always @(posedge clk) begin
        if (!rst)
            assert (gnt == expected);
        if (rst) begin
            expected <= 4'b0;
            next_priority <= 2'b0;
        end else begin
            expected <= decision;
            if (found)
                next_priority <= chosen + 2'd1;
        end
    end
endmodule
