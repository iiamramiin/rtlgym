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

    logic [LINES-1:0] valid;
    logic [TAG_W-1:0] tags [LINES];
    logic [2*DATA_W-1:0] lines [LINES];
    logic sending, receiving, replying;
    logic [TAG_W+INDEX_W:0] miss_addr;
    logic [DATA_W-1:0] response;

    wire [INDEX_W-1:0] index_now = cpu_req_addr[INDEX_W:1];
    wire [TAG_W-1:0] tag_now = cpu_req_addr[TAG_W+INDEX_W:INDEX_W+1];
    wire [INDEX_W-1:0] fill_index = miss_addr[INDEX_W:1];
    wire [2*DATA_W-1:0] hit_line = lines[index_now];
    wire hit = valid[index_now] && tags[index_now] == tag_now;
    wire lookup = cpu_req_valid && cpu_req_ready;
    wire send = mem_req_valid && mem_req_ready;
    wire fill = mem_rsp_valid && mem_rsp_ready;
    wire reply = cpu_rsp_valid && cpu_rsp_ready;

    assign inv_ready = !rst && !(sending || receiving || replying);
    assign cpu_req_ready = inv_ready && !inv_valid;
    assign mem_req_valid = !rst && sending;
    assign mem_req_addr = mem_req_valid ? miss_addr[TAG_W+INDEX_W:1] : '0;
    assign mem_rsp_ready = !rst && receiving;
    assign cpu_rsp_valid = !rst && replying;
    assign cpu_rsp_data = cpu_rsp_valid ? response : '0;

    // Each transaction stage owns a valid bit, set by the previous handshake.
    always_ff @(posedge clk) begin
        if (rst) begin
            sending <= 1'b0;
            receiving <= 1'b0;
            replying <= 1'b0;
            valid <= '0;
            miss_addr <= '0;
            response <= '0;
        end else begin
            sending <= (sending && !send) || (lookup && !hit);
            receiving <= (receiving && !fill) || send;
            replying <= (replying && !reply) || (lookup && hit) || fill;

            if (inv_valid && inv_ready) valid <= '0;
            if (lookup && !hit) miss_addr <= cpu_req_addr;
            if (lookup && hit)
                response <= cpu_req_addr[0] ? hit_line[2*DATA_W-1:DATA_W] : hit_line[DATA_W-1:0];
            if (fill) begin
                valid[fill_index] <= 1'b1;
                tags[fill_index] <= miss_addr[TAG_W+INDEX_W:INDEX_W+1];
                lines[fill_index] <= mem_rsp_data;
                response <= miss_addr[0] ? mem_rsp_data[2*DATA_W-1:DATA_W] : mem_rsp_data[DATA_W-1:0];
            end
        end
    end
endmodule
