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

    logic phase, b_waited, r_waited;
    wire permit = !rst && (0 == 0 || phase);
    wire b_show = (0 == 0 || b_waited);
    wire r_show = (0 == 0 || r_waited);
    wire inner_s_axi_arready;
    wire inner_s_axi_awready;
    wire [ID_W-1:0] inner_s_axi_bid;
    wire [1:0] inner_s_axi_bresp;
    wire inner_s_axi_bvalid;
    wire [31:0] inner_s_axi_rdata;
    wire [ID_W-1:0] inner_s_axi_rid;
    wire inner_s_axi_rlast;
    wire [1:0] inner_s_axi_rresp;
    wire inner_s_axi_rvalid;
    wire inner_s_axi_wready;
    wire core_bready = s_axi_bready && b_show;
    wire core_rready = s_axi_rready && r_show;
    always @(posedge clk) begin
        if (rst) begin phase<=0; b_waited<=0; r_waited<=0; end
        else begin
            phase<=!phase;
            if (!inner_s_axi_bvalid || core_bready) b_waited<=0; else b_waited<=1;
            if (!inner_s_axi_rvalid || core_rready) r_waited<=0; else r_waited<=1;
        end
    end
    assign s_axi_arready = inner_s_axi_arready && permit;
    assign s_axi_awready = inner_s_axi_awready && permit;
    assign s_axi_bid = inner_s_axi_bid;
    assign s_axi_bresp = inner_s_axi_bresp;
    assign s_axi_bvalid = inner_s_axi_bvalid && b_show;
    assign s_axi_rdata = inner_s_axi_rdata;
    assign s_axi_rid = inner_s_axi_rid;
    assign s_axi_rlast = inner_s_axi_rlast;
    assign s_axi_rresp = inner_s_axi_rresp;
    assign s_axi_rvalid = inner_s_axi_rvalid && r_show;
    assign s_axi_wready = inner_s_axi_wready && permit;
    axi4_core #(.ADDR_W(ADDR_W),.ID_W(ID_W),.LEN_W(LEN_W)) core (
        .clk(clk),
        .rst(rst),
        .s_axi_awid(s_axi_awid),
        .s_axi_awaddr(s_axi_awaddr),
        .s_axi_awlen(s_axi_awlen),
        .s_axi_awsize(s_axi_awsize),
        .s_axi_awburst(s_axi_awburst),
        .s_axi_awlock(s_axi_awlock),
        .s_axi_awcache(s_axi_awcache),
        .s_axi_awprot(s_axi_awprot),
        .s_axi_awqos(s_axi_awqos),
        .s_axi_awregion(s_axi_awregion),
        .s_axi_awvalid(s_axi_awvalid && permit),
        .s_axi_awready(inner_s_axi_awready),
        .s_axi_wdata(s_axi_wdata),
        .s_axi_wstrb(s_axi_wstrb),
        .s_axi_wlast(s_axi_wlast),
        .s_axi_wvalid(s_axi_wvalid && permit),
        .s_axi_wready(inner_s_axi_wready),
        .s_axi_bid(inner_s_axi_bid),
        .s_axi_bresp(inner_s_axi_bresp),
        .s_axi_bvalid(inner_s_axi_bvalid),
        .s_axi_bready(core_bready),
        .s_axi_arid(s_axi_arid),
        .s_axi_araddr(s_axi_araddr),
        .s_axi_arlen(s_axi_arlen),
        .s_axi_arsize(s_axi_arsize),
        .s_axi_arburst(s_axi_arburst),
        .s_axi_arlock(s_axi_arlock),
        .s_axi_arcache(s_axi_arcache),
        .s_axi_arprot(s_axi_arprot),
        .s_axi_arqos(s_axi_arqos),
        .s_axi_arregion(s_axi_arregion),
        .s_axi_arvalid(s_axi_arvalid && permit),
        .s_axi_arready(inner_s_axi_arready),
        .s_axi_rid(inner_s_axi_rid),
        .s_axi_rdata(inner_s_axi_rdata),
        .s_axi_rresp(inner_s_axi_rresp),
        .s_axi_rlast(inner_s_axi_rlast),
        .s_axi_rvalid(inner_s_axi_rvalid),
        .s_axi_rready(core_rready));
endmodule
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Ramin Rajaei

module axi4_core #(
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
    logic write_active, write_bad, last_bad;
    logic [ID_W-1:0] write_id;
    logic [LEN_W-1:0] write_rem, read_rem;
    logic [ADDR_W-3:0] write_word, next_read_word;
    logic aw_fire, w_fire, ar_fire, r_fire;
    logic aw_bad, ar_bad;
    assign aw_fire = s_axi_awvalid && s_axi_awready;
    assign w_fire = s_axi_wvalid && s_axi_wready;
    assign ar_fire = s_axi_arvalid && s_axi_arready;
    assign r_fire = s_axi_rvalid && s_axi_rready;
    assign aw_bad = bad_burst(s_axi_awaddr, s_axi_awlen, s_axi_awsize, s_axi_awburst, s_axi_awlock);
    assign ar_bad = bad_burst(s_axi_araddr, s_axi_arlen, s_axi_arsize, s_axi_arburst, s_axi_arlock);
    assign s_axi_arready = !rst && !s_axi_rvalid;

    assign s_axi_awready = !rst && !write_active && !s_axi_bvalid;
    assign s_axi_wready = !rst && write_active;
    assign last_bad = s_axi_wlast != (write_rem == '0);

    // The next unread word is fetched only when the current R beat transfers.
    always_ff @(posedge clk) begin
        if (rst) begin
            write_active <= 1'b0;
            write_bad <= 1'b0;
            write_id <= '0;
            write_rem <= '0;
            write_word <= '0;
            s_axi_bvalid <= 1'b0;
            s_axi_bid <= '0;
            for (int word_idx = 0; word_idx < WORDS; word_idx++)
                memory[word_idx] <= '0;
        end else begin
            if (s_axi_bvalid && s_axi_bready)
                s_axi_bvalid <= 1'b0;
            if (aw_fire) begin
                write_active <= 1'b1;
                write_bad <= aw_bad;
                write_id <= s_axi_awid;
                write_rem <= s_axi_awlen;
                write_word <= s_axi_awaddr[ADDR_W-1:2];
            end
            if (w_fire) begin
                if (!write_bad) begin
                    for (int lane = 0; lane < 4; lane++) begin
                        if (s_axi_wstrb[lane])
                            memory[write_word][8*lane +: 8] <= s_axi_wdata[8*lane +: 8];
                    end
                end
                if (write_rem == '0) begin
                    write_active <= 1'b0;
                    s_axi_bvalid <= 1'b1;
                    s_axi_bid <= write_id;
                end else begin
                    write_rem <= write_rem - 1'b1;
                    write_word <= write_word + 1'b1;
                end
            end
        end
    end

    // Keep framing errors separate from descriptor errors. WLAST never ends the burst.
    logic bad_last_seen;
    always_ff @(posedge clk) begin
        if (rst) begin
            bad_last_seen <= 1'b0;
            s_axi_bresp <= OKAY;
        end else begin
            if (aw_fire)
                bad_last_seen <= 1'b0;
            if (w_fire) begin
                bad_last_seen <= bad_last_seen || last_bad;
                if (write_rem == '0)
                    s_axi_bresp <= (write_bad || bad_last_seen || last_bad) ? SLVERR : OKAY;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            s_axi_rvalid <= 1'b0;
            s_axi_rid <= '0;
            s_axi_rdata <= '0;
            s_axi_rlast <= 1'b0;
            s_axi_rresp <= OKAY;
            read_rem <= '0;
            next_read_word <= '0;
        end else if (ar_fire) begin
            s_axi_rvalid <= 1'b1;
            s_axi_rid <= s_axi_arid;
            s_axi_rresp <= ar_bad ? SLVERR : OKAY;
            s_axi_rdata <= ar_bad ? 32'b0 : memory[s_axi_araddr[ADDR_W-1:2]];
            s_axi_rlast <= s_axi_arlen == '0;
            read_rem <= s_axi_arlen;
            next_read_word <= s_axi_araddr[ADDR_W-1:2];
        end else if (r_fire) begin
            if (s_axi_rlast) begin
                s_axi_rvalid <= 1'b0;
            end else begin
                read_rem <= read_rem - 1'b1;
                next_read_word <= next_read_word + 1'b1;
                s_axi_rdata <= (s_axi_rresp == OKAY) ? memory[next_read_word] : 32'b0;
                s_axi_rlast <= read_rem == LEN_W'(1);
            end
        end
    end
endmodule
