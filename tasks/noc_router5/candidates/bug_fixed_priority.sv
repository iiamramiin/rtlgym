module noc_router5 #(
    parameter logic [1:0] X = 2'd1,
    parameter logic [1:0] Y = 2'd1,
    parameter int PAYLOAD_W = 8
) (
    input  logic                       clk,
    input  logic                       rst,
    input  logic [4:0]                 in_valid,
    output logic [4:0]                 in_ready,
    input  logic [5*(4+PAYLOAD_W)-1:0]  in_flit,
    output logic [4:0]                 out_valid,
    input  logic [4:0]                 out_ready,
    output logic [5*(4+PAYLOAD_W)-1:0]  out_flit
);
    localparam int FLIT_W = 4 + PAYLOAD_W;
    localparam logic [2:0] NORTH = 3'd0;
    localparam logic [2:0] SOUTH = 3'd1;
    localparam logic [2:0] EAST  = 3'd2;
    localparam logic [2:0] WEST  = 3'd3;
    localparam logic [2:0] LOCAL_PORT = 3'd4;

    logic [2:0] route [5];
    logic [4:0] accepted [5];

    for (genvar src = 0; src < 5; src++) begin : g_route
        wire [1:0] dest_x = in_flit[src*FLIT_W + PAYLOAD_W+2 +: 2];
        wire [1:0] dest_y = in_flit[src*FLIT_W + PAYLOAD_W +: 2];
        assign route[src] = dest_x > X ? EAST :
                            dest_x < X ? WEST :
                            dest_y > Y ? NORTH :
                            dest_y < Y ? SOUTH : LOCAL_PORT;
        assign in_ready[src] = accepted[0][src] | accepted[1][src] | accepted[2][src] |
                               accepted[3][src] | accepted[4][src];
    end

    for (genvar dst = 0; dst < 5; dst++) begin : g_output
        logic occupied;
        logic [FLIT_W-1:0] data;
        logic [4:0] requests, eligible, grant;
        logic [FLIT_W-1:0] selected_flit;
        wire hold_slot = occupied && !out_ready[dst] && !rst;
        wire can_accept = !rst && (!occupied || out_ready[dst]);

        assign out_valid[dst] = occupied;
        assign out_flit[dst*FLIT_W +: FLIT_W] = data;
        assign accepted[dst] = grant;
        assign eligible = requests;

        for (genvar src = 0; src < 5; src++) begin : g_grant
            assign requests[src] = in_valid[src] && route[src] == 3'(dst);
            if (src == 0) begin : g_first
                assign grant[src] = can_accept && eligible[src];
            end else begin : g_later
                assign grant[src] = can_accept && eligible[src] && !(|eligible[src-1:0]);
            end
        end

        always_comb begin
            selected_flit = '0;
            for (int src = 0; src < 5; src++) begin
                selected_flit |= in_flit[src*FLIT_W +: FLIT_W] & {FLIT_W{grant[src]}};
            end
        end

        always_ff @(posedge clk) begin
            occupied <= hold_slot || (|grant);
            data <= selected_flit | (data & {FLIT_W{hold_slot}});
        end
    end
endmodule
