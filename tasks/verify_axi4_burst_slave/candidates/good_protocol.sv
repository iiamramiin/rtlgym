// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module rtl_checker #(
    parameter int ADDR_W = 3,
    parameter int ID_W   = 1,
    parameter int LEN_W  = 1
) (
    input  logic              clk,
    input  logic              rst,

    input  logic [ID_W-1:0]   s_axi_awid,
    input  logic [ADDR_W-1:0] s_axi_awaddr,
    input  logic [LEN_W-1:0]  s_axi_awlen,
    input  logic [2:0]        s_axi_awsize,
    input  logic [1:0]        s_axi_awburst,
    input  logic              s_axi_awlock,
    input  logic [3:0]        s_axi_awcache,
    input  logic [2:0]        s_axi_awprot,
    input  logic [3:0]        s_axi_awqos,
    input  logic [3:0]        s_axi_awregion,
    input  logic              s_axi_awvalid,
    input  logic              s_axi_awready,

    input  logic [31:0]       s_axi_wdata,
    input  logic [3:0]        s_axi_wstrb,
    input  logic              s_axi_wlast,
    input  logic              s_axi_wvalid,
    input  logic              s_axi_wready,

    input  logic [ID_W-1:0]   s_axi_bid,
    input  logic [1:0]        s_axi_bresp,
    input  logic              s_axi_bvalid,
    input  logic              s_axi_bready,

    input  logic [ID_W-1:0]   s_axi_arid,
    input  logic [ADDR_W-1:0] s_axi_araddr,
    input  logic [LEN_W-1:0]  s_axi_arlen,
    input  logic [2:0]        s_axi_arsize,
    input  logic [1:0]        s_axi_arburst,
    input  logic              s_axi_arlock,
    input  logic [3:0]        s_axi_arcache,
    input  logic [2:0]        s_axi_arprot,
    input  logic [3:0]        s_axi_arqos,
    input  logic [3:0]        s_axi_arregion,
    input  logic              s_axi_arvalid,
    input  logic              s_axi_arready,

    input  logic [ID_W-1:0]   s_axi_rid,
    input  logic [31:0]       s_axi_rdata,
    input  logic [1:0]        s_axi_rresp,
    input  logic              s_axi_rlast,
    input  logic              s_axi_rvalid,
    input  logic              s_axi_rready
);
    logic started = 0;
    logic [31:0] mem [0:1];
    logic write_active, write_response, write_bad, write_last_bad;
    logic write_word, write_id, write_remaining;
    logic expected_bid;
    logic [1:0] expected_bresp;
    logic read_active, read_bad, read_remaining, read_next_word, expected_rid;
    logic [31:0] expected_rdata;
    logic aw_blocked, w_blocked, ar_blocked, b_waiting, r_waiting;
    logic held_b, held_r;
    logic prior_bid, prior_rid, prior_rlast;
    logic [1:0] prior_bresp, prior_rresp;
    logic [31:0] prior_rdata;

    function automatic logic invalid_descriptor(
        input logic [2:0] addr, input logic len,
        input logic [2:0] size, input logic [1:0] burst, input logic lock
    );
        logic [3:0] last_address;
        last_address = {1'b0,addr} + {1'b0,len,2'b00};
        invalid_descriptor = addr[1:0] != 0 || size != 2 || burst != 1
                           || lock || last_address >= 8;
    endfunction

    always @* begin
        if (rst) begin
            assert(!s_axi_awready);
            assert(!s_axi_wready);
            assert(!s_axi_arready);
        end
    end

    always @(posedge clk) begin
        if (started && !rst) begin
            if (write_active || write_response) begin assert(!s_axi_awready); end
            else begin assert(!aw_blocked || s_axi_awready); end
            if (!write_active) begin assert(!s_axi_wready); end
            else begin assert(!w_blocked || s_axi_wready); end
            if (read_active) begin assert(!s_axi_arready); end
            else begin assert(!ar_blocked || s_axi_arready); end
            if (write_response) assert(s_axi_bvalid || !b_waiting);
            if (read_active) assert(s_axi_rvalid || !r_waiting);
            if (s_axi_bvalid) begin
                assert(write_response);
                assert(s_axi_bid == expected_bid);
                assert(s_axi_bresp == expected_bresp);
            end
            if (s_axi_rvalid) begin
                assert(read_active);
                assert(s_axi_rid == expected_rid);
                assert(s_axi_rresp == (read_bad ? 2'b10 : 2'b00));
                assert(s_axi_rlast == !read_remaining);
                assert(s_axi_rdata == expected_rdata);
            end
            if (held_b) begin
                assert(s_axi_bvalid);
                assert(s_axi_bid == prior_bid && s_axi_bresp == prior_bresp);
            end
            if (held_r) begin
                assert(s_axi_rvalid);
                assert(s_axi_rid == prior_rid && s_axi_rresp == prior_rresp);
                assert(s_axi_rlast == prior_rlast && s_axi_rdata == prior_rdata);
            end
        end
        if (rst) begin
            started<=1;
            write_active<=0; write_response<=0; write_bad<=0; write_last_bad<=0;
            write_word<=0; write_id<=0; write_remaining<=0;
            expected_bid<=0; expected_bresp<=0;
            read_active<=0; read_bad<=0; read_remaining<=0; read_next_word<=0;
            expected_rid<=0; expected_rdata<=0;
            aw_blocked<=0; w_blocked<=0; ar_blocked<=0; b_waiting<=0; r_waiting<=0;
            held_b<=0; held_r<=0; prior_bid<=0; prior_rid<=0; prior_rlast<=0;
            prior_bresp<=0; prior_rresp<=0; prior_rdata<=0;
            mem[0]<=0; mem[1]<=0;
        end else begin
            aw_blocked <= !write_active && !write_response && !s_axi_awready;
            w_blocked <= write_active && !s_axi_wready;
            ar_blocked <= !read_active && !s_axi_arready;
            b_waiting <= write_response && !s_axi_bvalid;
            r_waiting <= read_active && !s_axi_rvalid;
            held_b<=s_axi_bvalid && !s_axi_bready;
            held_r<=s_axi_rvalid && !s_axi_rready;
            prior_bid<=s_axi_bid; prior_bresp<=s_axi_bresp;
            prior_rid<=s_axi_rid; prior_rresp<=s_axi_rresp;
            prior_rlast<=s_axi_rlast; prior_rdata<=s_axi_rdata;
            if (s_axi_awvalid && s_axi_awready) begin
                write_active<=1; write_bad<=invalid_descriptor(s_axi_awaddr,s_axi_awlen,
                    s_axi_awsize,s_axi_awburst,s_axi_awlock);
                write_last_bad<=0; write_word<=s_axi_awaddr[2];
                write_id<=s_axi_awid; write_remaining<=s_axi_awlen;
            end
            if (s_axi_wvalid && s_axi_wready) begin
                write_last_bad<=write_last_bad || (s_axi_wlast != !write_remaining);
                if (!write_bad) begin
                    for(integer lane=0;lane<4;lane=lane+1) begin
                        if(s_axi_wstrb[lane]) mem[write_word][(lane << 3) +: 8]<=s_axi_wdata[(lane << 3) +: 8];
                    end
                end
                if (write_remaining) begin write_remaining<=0; write_word<=!write_word; end
                else begin
                    write_active<=0; write_response<=1;
                    expected_bid<=write_id;
                    expected_bresp <= (write_bad || write_last_bad || (s_axi_wlast != 1'b1))
                                      ? 2'b10 : 2'b00;
                    b_waiting<=0;
                end
            end
            if (s_axi_bvalid && s_axi_bready) write_response<=0;
            if (s_axi_arvalid && s_axi_arready) begin
                read_active<=1; read_remaining<=s_axi_arlen; expected_rid<=s_axi_arid;
                read_bad<=invalid_descriptor(s_axi_araddr,s_axi_arlen,
                    s_axi_arsize,s_axi_arburst,s_axi_arlock);
                expected_rdata<=invalid_descriptor(s_axi_araddr,s_axi_arlen,
                    s_axi_arsize,s_axi_arburst,s_axi_arlock) ? 32'b0 : mem[s_axi_araddr[2]];
                read_next_word<=!s_axi_araddr[2]; r_waiting<=0;
            end
            if (s_axi_rvalid && s_axi_rready) begin
                if (read_remaining) begin
                    read_remaining<=0; expected_rdata<=read_bad ? 32'b0 : mem[read_next_word];
                    read_next_word<=!read_next_word; r_waiting<=0;
                end else read_active<=0;
            end
        end
    end
endmodule
