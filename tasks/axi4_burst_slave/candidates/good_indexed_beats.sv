// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module axi4_burst_slave #(
    parameter int ADDR_W = 8,
    parameter int ID_W   = 2,
    parameter int LEN_W  = 8
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
    output logic              s_axi_awready,

    input  logic [31:0]       s_axi_wdata,
    input  logic [3:0]        s_axi_wstrb,
    input  logic              s_axi_wlast,
    input  logic              s_axi_wvalid,
    output logic              s_axi_wready,

    output logic [ID_W-1:0]   s_axi_bid,
    output logic [1:0]        s_axi_bresp,
    output logic              s_axi_bvalid,
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
    output logic              s_axi_arready,

    output logic [ID_W-1:0]   s_axi_rid,
    output logic [31:0]       s_axi_rdata,
    output logic [1:0]        s_axi_rresp,
    output logic              s_axi_rlast,
    output logic              s_axi_rvalid,
    input  logic              s_axi_rready
);
    localparam int WORDS = 1 << (ADDR_W - 2);
    localparam int RANGE_W = 1 + ((ADDR_W > LEN_W + 2) ? ADDR_W : LEN_W + 2);
    localparam logic [1:0] OKAY = 2'b00, SLVERR = 2'b10;

    logic unused_attrs;
    assign unused_attrs = ^{s_axi_awcache, s_axi_awprot, s_axi_awqos, s_axi_awregion,
                            s_axi_arcache, s_axi_arprot, s_axi_arqos, s_axi_arregion};

    function automatic logic bad_burst(
        input logic [ADDR_W-1:0] addr,
        input logic [LEN_W-1:0] len,
        input logic [2:0] size,
        input logic [1:0] burst,
        input logic lock
    );
        logic [RANGE_W-1:0] last_addr;
        last_addr = RANGE_W'(addr) + (RANGE_W'(len) << 2);
        bad_burst = addr[1:0] != 2'b00 || size != 3'd2 || burst != 2'b01 || lock
                    || (last_addr >> ADDR_W) != '0;
    endfunction

    logic [31:0] memory [WORDS];
    logic [ID_W-1:0] pending_id;
    logic [LEN_W-1:0] write_len, read_len, write_index, read_index, next_read_index;
    logic [ADDR_W-3:0] write_base, read_base, write_address, read_address;
    logic [31:0] mask;
    logic collecting, malformed, framing_error, is_last_write, last_matches;

    logic aw_fire, w_fire, ar_fire, r_fire;
    logic aw_bad, ar_bad;
    assign aw_fire = s_axi_awvalid && s_axi_awready;
    assign w_fire = s_axi_wvalid && s_axi_wready;
    assign ar_fire = s_axi_arvalid && s_axi_arready;
    assign r_fire = s_axi_rvalid && s_axi_rready;
    assign aw_bad = bad_burst(s_axi_awaddr, s_axi_awlen, s_axi_awsize, s_axi_awburst, s_axi_awlock);
    assign ar_bad = bad_burst(s_axi_araddr, s_axi_arlen, s_axi_arsize, s_axi_arburst, s_axi_arlock);
    assign s_axi_arready = !rst && !s_axi_rvalid;

    assign s_axi_awready = !rst && !collecting && !s_axi_bvalid;
    assign s_axi_wready = !rst && collecting;
    assign is_last_write = write_index == write_len;
    assign last_matches = s_axi_wlast == is_last_write;

    // Keep the base immutable and derive the RAM index from the accepted-beat count.
    assign write_address = write_base + (ADDR_W-2)'(write_index);
    assign next_read_index = read_index + 1'b1;
    assign read_address = read_base + (ADDR_W-2)'(next_read_index);

    for (genvar lane = 0; lane < 4; lane++) begin : gen_mask
        assign mask[8*lane +: 8] = {8{s_axi_wstrb[lane]}};
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int word_idx = 0; word_idx < WORDS; word_idx++)
                memory[word_idx] <= '0;
        end else if (w_fire && !malformed) begin
            memory[write_address] <= (memory[write_address] & ~mask) | (s_axi_wdata & mask);
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            collecting <= 1'b0;
            malformed <= 1'b0;
            framing_error <= 1'b0;
            write_index <= '0;
            write_len <= '0;
            write_base <= '0;
            pending_id <= '0;
            s_axi_bvalid <= 1'b0;
            s_axi_bresp <= OKAY;
            s_axi_bid <= '0;
        end else begin
            if (s_axi_bready)
                s_axi_bvalid <= 1'b0;
            if (aw_fire) begin
                collecting <= 1'b1;
                malformed <= aw_bad;
                framing_error <= 1'b0;
                write_index <= '0;
                write_len <= s_axi_awlen;
                write_base <= s_axi_awaddr[ADDR_W-1:2];
                pending_id <= s_axi_awid;
            end else if (w_fire) begin
                write_index <= write_index + 1'b1;
                framing_error <= framing_error || !last_matches;
                if (is_last_write) begin
                    collecting <= 1'b0;
                    s_axi_bvalid <= 1'b1;
                    s_axi_bid <= pending_id;
                    s_axi_bresp <= (malformed || framing_error || !last_matches) ? SLVERR : OKAY;
                end
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            read_base <= '0;
            read_len <= '0;
            read_index <= '0;
            s_axi_rvalid <= 1'b0;
            s_axi_rid <= '0;
            s_axi_rdata <= '0;
            s_axi_rresp <= OKAY;
            s_axi_rlast <= 1'b0;
        end else if (r_fire && s_axi_rlast) begin
            s_axi_rvalid <= 1'b0;
        end else if (ar_fire || r_fire) begin
            if (ar_fire) begin
                read_base <= s_axi_araddr[ADDR_W-1:2];
                read_len <= s_axi_arlen;
                read_index <= '0;
                s_axi_rvalid <= 1'b1;
                s_axi_rid <= s_axi_arid;
                s_axi_rdata <= ar_bad ? 32'b0 : memory[s_axi_araddr[ADDR_W-1:2]];
                s_axi_rresp <= ar_bad ? SLVERR : OKAY;
                s_axi_rlast <= s_axi_arlen == '0;
            end else begin
                read_index <= next_read_index;
                s_axi_rdata <= (s_axi_rresp == OKAY) ? memory[read_address] : 32'b0;
                s_axi_rlast <= next_read_index == read_len;
            end
        end
    end
endmodule
