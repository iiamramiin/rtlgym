// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module cache_controller #(
    parameter integer DATA_W = 2,
    parameter integer TAG_W = 1,
    parameter integer INDEX_W = 1
) (
    input wire clk, rst, inv_valid,
    output wire inv_ready,
    input wire cpu_req_valid,
    output wire cpu_req_ready,
    input wire [TAG_W+INDEX_W:0] cpu_req_addr,
    output wire cpu_rsp_valid,
    input wire cpu_rsp_ready,
    output wire [DATA_W-1:0] cpu_rsp_data,
    output wire mem_req_valid,
    input wire mem_req_ready,
    output wire [TAG_W+INDEX_W-1:0] mem_req_addr,
    input wire mem_rsp_valid,
    output wire mem_rsp_ready,
    input wire [2*DATA_W-1:0] mem_rsp_data
);
    localparam integer HIT_DELAY = 2;
    localparam integer MISS_DELAY = 1;
    localparam integer REFILL_DELAY = 0;
    localparam integer REARM_DELAY = 0;
    localparam integer IDLE_PATTERN = 3;
    localparam integer LINES = 1 << INDEX_W;
    localparam [2:0] IDLE=0, START=1, SEND=2, REFILL=3, WAIT_RESPONSE=4, RESPONSE=5, REARM=6;
    reg [2:0] state;
    reg [1:0] delay_left;
    reg [LINES-1:0] valid;
    reg [TAG_W-1:0] tags [0:LINES-1];
    reg [2*DATA_W-1:0] words [0:LINES-1];
    reg [TAG_W+INDEX_W-1:0] pending_line;
    reg pending_offset;
    reg [DATA_W-1:0] result_word;
    wire [INDEX_W-1:0] req_index = cpu_req_addr[INDEX_W:1];
    wire [TAG_W-1:0] req_tag = cpu_req_addr[TAG_W+INDEX_W:INDEX_W+1];
    wire [INDEX_W-1:0] pending_index = pending_line[INDEX_W-1:0];
    wire hit = valid[req_index] && tags[req_index] == req_tag;
    wire [2*DATA_W-1:0] hit_line = words[req_index];

    assign inv_ready = !rst && state == IDLE;
    assign cpu_req_ready = inv_ready && !inv_valid;
    assign cpu_rsp_valid = !rst && state == RESPONSE;
    assign cpu_rsp_data = cpu_rsp_valid ? result_word : DATA_W'(IDLE_PATTERN);
    assign mem_req_valid = !rst && state == SEND;
    assign mem_req_addr = mem_req_valid ? pending_line : (TAG_W+INDEX_W)'(IDLE_PATTERN);
    assign mem_rsp_ready = !rst && state == REFILL;

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            delay_left <= 0;
            valid <= 0;
            pending_line <= 0;
            pending_offset <= 0;
            result_word <= 0;
            for (integer entry=0; entry<LINES; entry=entry+1) begin
                tags[entry] <= 0;
                words[entry] <= 0;
            end
        end else begin
            case (state)
                IDLE: begin
                    if (inv_valid) begin
                        valid <= 0;
                    end else if (cpu_req_valid) begin
                        if (hit) begin
                            result_word <=
                                cpu_req_addr[0] ? hit_line[2*DATA_W-1:DATA_W] : hit_line[DATA_W-1:0];
                            delay_left <= HIT_DELAY;
                            state <= HIT_DELAY == 0 ? RESPONSE : WAIT_RESPONSE;
                        end else begin
                            pending_line <= cpu_req_addr[TAG_W+INDEX_W:1];
                            pending_offset <= cpu_req_addr[0];
                            delay_left <= MISS_DELAY;
                            state <= MISS_DELAY == 0 ? SEND : START;
                        end
                    end
                end
                START: begin
                    if (delay_left == 1) state <= SEND;
                    else delay_left <= delay_left - 1'b1;
                end
                SEND: if (mem_req_ready) state <= REFILL;
                REFILL: if (mem_rsp_valid) begin
                    valid[pending_index] <= 1'b1;
                    tags[pending_index] <= pending_line[TAG_W+INDEX_W-1:INDEX_W];
                    words[pending_index] <= mem_rsp_data;
                    result_word <=
                        pending_offset ? mem_rsp_data[2*DATA_W-1:DATA_W] : mem_rsp_data[DATA_W-1:0];
                    delay_left <= REFILL_DELAY;
                    state <= REFILL_DELAY == 0 ? RESPONSE : WAIT_RESPONSE;
                end
                WAIT_RESPONSE: begin
                    if (delay_left == 1) state <= RESPONSE;
                    else delay_left <= delay_left - 1'b1;
                end
                RESPONSE: if (cpu_rsp_ready) state <= REARM_DELAY == 0 ? IDLE : REARM;
                REARM: state <= IDLE;
                default: state <= IDLE;
            endcase
        end
    end
endmodule
