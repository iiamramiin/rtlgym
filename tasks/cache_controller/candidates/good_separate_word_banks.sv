// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module cache_controller #(
    parameter int DATA_W = 32,
    parameter int TAG_W = 5,
    parameter int INDEX_W = 2
) (
    input  logic                     clk,
    input  logic                     rst,
    input  logic                     inv_valid,
    output logic                     inv_ready,
    input  logic                     cpu_req_valid,
    output logic                     cpu_req_ready,
    input  logic [TAG_W+INDEX_W:0]   cpu_req_addr,
    output logic                     cpu_rsp_valid,
    input  logic                     cpu_rsp_ready,
    output logic [DATA_W-1:0]        cpu_rsp_data,
    output logic                     mem_req_valid,
    input  logic                     mem_req_ready,
    output logic [TAG_W+INDEX_W-1:0] mem_req_addr,
    input  logic                     mem_rsp_valid,
    output logic                     mem_rsp_ready,
    input  logic [2*DATA_W-1:0]      mem_rsp_data
);
    localparam int LINES = 1 << INDEX_W;
    typedef enum logic [1:0] { IDLE, SEND_REQUEST, WAIT_REFILL, RESPOND } phase_t;
    phase_t phase;

    logic [LINES-1:0] valid;
    logic [TAG_W-1:0] tags [LINES];
    logic [DATA_W-1:0] low_words [LINES];
    logic [DATA_W-1:0] high_words [LINES];
    logic [TAG_W+INDEX_W-1:0] pending_line;
    logic pending_offset;
    logic [DATA_W-1:0] response;

    wire [INDEX_W-1:0] request_index = cpu_req_addr[INDEX_W:1];
    wire [TAG_W-1:0] request_tag = cpu_req_addr[TAG_W+INDEX_W:INDEX_W+1];
    wire [INDEX_W-1:0] pending_index = pending_line[INDEX_W-1:0];
    wire hit = valid[request_index] && tags[request_index] == request_tag;
    wire request_offset = cpu_req_addr[0];
    // The word offset selects a bank before the indexed word read.
    wire [DATA_W-1:0] hit_word = request_offset ? high_words[request_index] : low_words[request_index];

    assign inv_ready = !rst && phase == IDLE;
    assign cpu_req_ready = inv_ready && !inv_valid;
    assign cpu_rsp_valid = !rst && phase == RESPOND;
    assign cpu_rsp_data = cpu_rsp_valid ? response : '0;
    assign mem_req_valid = !rst && phase == SEND_REQUEST;
    assign mem_req_addr = mem_req_valid ? pending_line : '0;
    assign mem_rsp_ready = !rst && phase == WAIT_REFILL;

    always_ff @(posedge clk) begin
        if (rst) begin
            phase <= IDLE;
            valid <= '0;
            pending_line <= '0;
            pending_offset <= 1'b0;
            response <= '0;
        end else begin
            case (phase)
                IDLE: begin
                    if (inv_valid) begin
                        valid <= '0;
                    end else if (cpu_req_valid) begin
                        if (hit) begin
                            response <= hit_word;
                            phase <= RESPOND;
                        end else begin
                            pending_line <= cpu_req_addr[TAG_W+INDEX_W:1];
                            pending_offset <= request_offset;
                            phase <= SEND_REQUEST;
                        end
                    end
                end
                SEND_REQUEST: if (mem_req_ready) phase <= WAIT_REFILL;
                WAIT_REFILL: if (mem_rsp_valid) begin
                    valid[pending_index] <= 1'b1;
                    tags[pending_index] <= pending_line[TAG_W+INDEX_W-1:INDEX_W];
                    low_words[pending_index] <= mem_rsp_data[DATA_W-1:0];
                    high_words[pending_index] <= mem_rsp_data[2*DATA_W-1:DATA_W];
                    response <= pending_offset ? mem_rsp_data[2*DATA_W-1:DATA_W] : mem_rsp_data[DATA_W-1:0];
                    phase <= RESPOND;
                end
                RESPOND: if (cpu_rsp_ready) phase <= IDLE;
                default: phase <= IDLE;
            endcase
        end
    end
endmodule
