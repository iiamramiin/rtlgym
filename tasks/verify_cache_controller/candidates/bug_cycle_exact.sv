// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module rtl_checker #(
    parameter integer DATA_W = 2,
    parameter integer TAG_W = 1,
    parameter integer INDEX_W = 1
) (
    input logic clk, rst, inv_valid, inv_ready,
    input logic cpu_req_valid, cpu_req_ready,
    input logic [TAG_W+INDEX_W:0] cpu_req_addr,
    input logic cpu_rsp_valid, cpu_rsp_ready,
    input logic [DATA_W-1:0] cpu_rsp_data,
    input logic mem_req_valid, mem_req_ready,
    input logic [TAG_W+INDEX_W-1:0] mem_req_addr,
    input logic mem_rsp_valid, mem_rsp_ready,
    input logic [2*DATA_W-1:0] mem_rsp_data
);
    localparam integer LINES = 1 << INDEX_W;
    localparam [1:0] IDLE=0, NEED_REQUEST=1, NEED_REFILL=2, NEED_RESPONSE=3;
    logic [1:0] stage;
    logic [1:0] age;
    logic idle_age;
    logic [LINES-1:0] valid;
    logic [TAG_W-1:0] tags [0:LINES-1];
    logic [2*DATA_W-1:0] lines [0:LINES-1];
    logic [TAG_W+INDEX_W-1:0] pending_line;
    logic pending_offset;
    logic [DATA_W-1:0] expected_word;
    logic held_cpu, held_memory;
    logic [DATA_W-1:0] held_word;
    logic [TAG_W+INDEX_W-1:0] held_address;
    logic [INDEX_W-1:0] request_index, refill_index;
    logic [TAG_W-1:0] request_tag;
    logic [2*DATA_W-1:0] request_line;
    assign request_index = cpu_req_addr[INDEX_W:1];
    assign request_tag = cpu_req_addr[TAG_W+INDEX_W:INDEX_W+1];
    assign refill_index = pending_line[INDEX_W-1:0];
    assign request_line = lines[request_index];

    always @(posedge clk) begin
        if (rst) begin
            assert (!inv_ready && !cpu_req_ready && !cpu_rsp_valid);
            assert (!mem_req_valid && !mem_rsp_ready);
            stage <= IDLE;
            age <= 0;
            idle_age <= 1;
            valid <= 0;
            pending_line <= 0;
            pending_offset <= 0;
            expected_word <= 0;
            held_cpu <= 0;
            held_memory <= 0;
            held_word <= 0;
            held_address <= 0;
            for (integer i=0; i<LINES; i=i+1) begin
                tags[i] <= 0;
                lines[i] <= 0;
            end
        end else begin
            assert (cpu_req_ready == (inv_ready && !inv_valid));
            assert (!inv_ready || stage == IDLE);
            assert (!mem_req_valid || stage == NEED_REQUEST);
            assert (mem_rsp_ready == (stage == NEED_REFILL));
            assert (!cpu_rsp_valid || stage == NEED_RESPONSE);
            if (held_cpu) begin
                assert (cpu_rsp_valid);
                assert (cpu_rsp_data == held_word);
            end
            if (held_memory) begin
                assert (mem_req_valid);
                assert (mem_req_addr == held_address);
            end
            held_cpu <= cpu_rsp_valid && !cpu_rsp_ready;
            held_memory <= mem_req_valid && !mem_req_ready;
            held_word <= cpu_rsp_data;
            held_address <= mem_req_addr;

            if (stage == IDLE) begin
                if (idle_age) assert (inv_ready);
                idle_age <= 1;
                if (inv_valid && inv_ready) valid <= 0;
                if (cpu_req_valid && cpu_req_ready) begin
                    age <= 0;
                    if (valid[request_index] && tags[request_index] == request_tag) begin
                        expected_word <= cpu_req_addr[0] ? request_line[2*DATA_W-1:DATA_W] : request_line[DATA_W-1:0];
                        stage <= NEED_RESPONSE;
                    end else begin
                        pending_line <= cpu_req_addr[TAG_W+INDEX_W:1];
                        pending_offset <= cpu_req_addr[0];
                        stage <= NEED_REQUEST;
                    end
                end
            end else if (stage == NEED_REQUEST) begin
                assert (mem_req_valid);
                if (age < 2) age <= age + 1'b1;
                if (mem_req_valid) assert (mem_req_addr == pending_line);
                if (mem_req_valid && mem_req_ready) stage <= NEED_REFILL;
            end else if (stage == NEED_REFILL) begin
                if (mem_rsp_valid && mem_rsp_ready) begin
                    valid[refill_index] <= 1'b1;
                    tags[refill_index] <= pending_line[TAG_W+INDEX_W-1:INDEX_W];
                    lines[refill_index] <= mem_rsp_data;
                    expected_word <= pending_offset ? mem_rsp_data[2*DATA_W-1:DATA_W] : mem_rsp_data[DATA_W-1:0];
                    stage <= NEED_RESPONSE;
                    age <= 0;
                end
            end else begin
                assert (cpu_rsp_valid);
                if (age < 2) age <= age + 1'b1;
                if (cpu_rsp_valid) assert (cpu_rsp_data == expected_word);
                if (cpu_rsp_valid && cpu_rsp_ready) begin
                    stage <= IDLE;
                    idle_age <= 0;
                end
            end
        end
    end
endmodule
