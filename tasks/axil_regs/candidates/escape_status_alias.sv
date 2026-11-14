module axil_regs (
    input  logic        clk,
    input  logic        rst,
    input  logic [31:0] status_in,
    input  logic [31:0] irq_set,

    input  logic [3:0]  s_axi_awaddr,
    input  logic [2:0]  s_axi_awprot,
    input  logic        s_axi_awvalid,
    output logic        s_axi_awready,

    input  logic [31:0] s_axi_wdata,
    input  logic [3:0]  s_axi_wstrb,
    input  logic        s_axi_wvalid,
    output logic        s_axi_wready,

    output logic [1:0]  s_axi_bresp,
    output logic        s_axi_bvalid,
    input  logic        s_axi_bready,

    input  logic [3:0]  s_axi_araddr,
    input  logic [2:0]  s_axi_arprot,
    input  logic        s_axi_arvalid,
    output logic        s_axi_arready,

    output logic [31:0] s_axi_rdata,
    output logic [1:0]  s_axi_rresp,
    output logic        s_axi_rvalid,
    input  logic        s_axi_rready
);
    localparam logic [1:0] OKAY = 2'b00;
    localparam logic [1:0] SLVERR = 2'b10;

    logic [31:0] ctrl, scratch, irq;
    logic have_aw, have_w, commit_write;
    logic [3:0] addr_q, strb_q;
    logic [31:0] data_q, byte_en;
    logic unused_prot;

    assign unused_prot = ^{s_axi_awprot, s_axi_arprot};
    assign s_axi_awready = !rst && !have_aw && !s_axi_bvalid;
    assign s_axi_wready = !rst && !have_w && !s_axi_bvalid;
    assign s_axi_arready = !rst && !s_axi_rvalid;
    assign commit_write = have_aw && have_w;

    for (genvar lane = 0; lane < 4; lane++) begin : gen_byte_en
        assign byte_en[8*lane +: 8] = {8{strb_q[lane]}};
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            ctrl <= '0;
            scratch <= '0;
            irq <= '0;
            have_aw <= 1'b0;
            have_w <= 1'b0;
            addr_q <= '0;
            data_q <= '0;
            strb_q <= '0;
            s_axi_bresp <= OKAY;
            s_axi_bvalid <= 1'b0;
            s_axi_rdata <= '0;
            s_axi_rresp <= OKAY;
            s_axi_rvalid <= 1'b0;
        end else begin
            irq <= irq | irq_set;

            if (s_axi_awvalid && s_axi_awready) begin
                have_aw <= 1'b1;
                addr_q <= s_axi_awaddr;
            end
            if (s_axi_wvalid && s_axi_wready) begin
                have_w <= 1'b1;
                data_q <= s_axi_wdata;
                strb_q <= s_axi_wstrb;
            end

            if (s_axi_bvalid && s_axi_bready)
                s_axi_bvalid <= 1'b0;

            if (commit_write) begin
                have_aw <= 1'b0;
                have_w <= 1'b0;
                s_axi_bvalid <= 1'b1;
                s_axi_bresp <= OKAY;
                case (addr_q)
                    4'h0: ctrl <= (ctrl & ~byte_en) | (data_q & byte_en);
                    4'h8: scratch <= (scratch & ~byte_en) | (data_q & byte_en);
                    4'hc: irq <= (irq & ~(data_q & byte_en)) | irq_set;
                    default: s_axi_bresp <= SLVERR;
                endcase
            end

            if (s_axi_rvalid && s_axi_rready)
                s_axi_rvalid <= 1'b0;

            if (s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid <= 1'b1;
                s_axi_rresp <= OKAY;
                case (s_axi_araddr)
                    4'h0: s_axi_rdata <= ctrl;
                    4'h4, 4'h5: s_axi_rdata <= status_in;
                    4'h8: s_axi_rdata <= scratch;
                    4'hc: s_axi_rdata <= irq;
                    default: begin
                        s_axi_rdata <= '0;
                        s_axi_rresp <= SLVERR;
                    end
                endcase
            end
        end
    end
endmodule
