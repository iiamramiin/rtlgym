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
endmodule
