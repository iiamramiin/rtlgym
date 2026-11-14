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

    // The state bits encode which of the independently accepted halves is present.
    localparam logic [1:0] EMPTY = 2'b00, ADDRESS = 2'b01, DATA = 2'b10, BOTH = 2'b11;

    logic [1:0] write_state;
    logic [3:0] saved_addr;
    logic [31:0] enabled_data, enable_mask;
    logic [31:0] ctrl, scratch, irq;
    logic got_address, got_data, got_read;
    logic unused_prot;

    assign unused_prot = ^{s_axi_awprot, s_axi_arprot};
    assign s_axi_awready = !rst && !write_state[0] && !s_axi_bvalid;
    assign s_axi_wready = !rst && !write_state[1] && !s_axi_bvalid;
    assign s_axi_arready = !rst && !s_axi_rvalid;

    assign got_address = s_axi_awvalid && s_axi_awready;
    assign got_data = s_axi_wvalid && s_axi_wready;
    assign got_read = s_axi_arvalid && s_axi_arready;

    always_ff @(posedge clk) begin
        if (rst) begin
            write_state <= EMPTY;
            saved_addr <= 4'h0;
        end else begin
            if (got_address)
                saved_addr <= s_axi_awaddr;
            case (write_state)
                EMPTY: begin
                    if (got_address && got_data)
                        write_state <= BOTH;
                    else if (got_address)
                        write_state <= ADDRESS;
                    else if (got_data)
                        write_state <= DATA;
                end
                ADDRESS: if (got_data) write_state <= BOTH;
                DATA: if (got_address) write_state <= BOTH;
                BOTH: write_state <= EMPTY;
                default: write_state <= EMPTY;
            endcase
        end
    end

    // The write channel stores only data enabled by WSTRB.
    for (genvar lane = 0; lane < 4; lane++) begin : gen_wbuf
        always_ff @(posedge clk) begin
            if (rst) begin
                enable_mask[8*lane +: 8] <= '0;
                enabled_data[8*lane +: 8] <= '0;
            end else if (got_data) begin
                enable_mask[8*lane +: 8] <= {8{s_axi_wstrb[lane]}};
                enabled_data[8*lane +: 8] <= s_axi_wstrb[lane] ? s_axi_wdata[8*lane +: 8] : '0;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            ctrl <= '0;
            scratch <= '0;
            irq <= '0;
            s_axi_bvalid <= 1'b0;
            s_axi_bresp <= OKAY;
        end else begin
            if (s_axi_bready)
                s_axi_bvalid <= 1'b0;
            if (write_state == BOTH) begin
                s_axi_bvalid <= 1'b1;
                s_axi_bresp <= (saved_addr == 4'h0 || saved_addr == 4'h8 || saved_addr == 4'hc)
                               ? OKAY : SLVERR;
                if (saved_addr == 4'h0)
                    ctrl <= (ctrl & ~enable_mask) | enabled_data;
                if (saved_addr == 4'h8)
                    scratch <= (scratch & ~enable_mask) | enabled_data;
            end
            irq <= (irq & ~((write_state == BOTH && saved_addr == 4'hc) ? enabled_data : 32'b0))
                   | irq_set;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            s_axi_rdata <= '0;
            s_axi_rresp <= OKAY;
            s_axi_rvalid <= 1'b0;
        end else begin
            if (s_axi_rready)
                s_axi_rvalid <= 1'b0;
            if (got_read) begin
                s_axi_rvalid <= 1'b1;
                s_axi_rresp <= (s_axi_araddr == 4'h0 || s_axi_araddr == 4'h4 ||
                                s_axi_araddr == 4'h8 || s_axi_araddr == 4'hc) ? OKAY : SLVERR;
                s_axi_rdata <= ((s_axi_araddr == 4'h0) ? ctrl      : 32'b0)
                             | ((s_axi_araddr == 4'h4) ? status_in : 32'b0)
                             | ((s_axi_araddr == 4'h8) ? scratch   : 32'b0)
                             | ((s_axi_araddr == 4'hc) ? irq       : 32'b0);
            end
        end
    end
endmodule
