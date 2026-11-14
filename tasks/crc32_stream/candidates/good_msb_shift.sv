module crc32_stream (
    input  logic        clk,
    input  logic        rst,
    input  logic        start,
    input  logic        in_valid,
    input  logic [7:0]  data,
    output logic        out_valid,
    output logic [31:0] crc
);
    // Store the remainder in normal-polynomial order rather than reflected order.
    logic [31:0] remainder;

    function automatic logic [31:0] update_byte(
        input logic [31:0] initial_remainder,
        input logic [7:0] byte_data
    );
        logic [31:0] value;
        logic feedback;
        begin
            value = initial_remainder;
            for (int i = 0; i < 8; i++) begin
                feedback = value[31] ^ byte_data[i];
                value = (value << 1) ^ (feedback ? 32'h04C1_1DB7 : 32'd0);
            end
            update_byte = value;
        end
    endfunction

    always_ff @(posedge clk) begin
        if (rst) begin
            remainder <= '1;
            out_valid <= 1'b0;
        end else begin
            out_valid <= in_valid;
            if (in_valid) begin
                remainder <= update_byte(start ? 32'hFFFF_FFFF : remainder, data);
            end else if (start) begin
                remainder <= '1;
            end
        end
    end

    for (genvar i = 0; i < 32; i++) begin : gen_crc_bits
        assign crc[i] = ~remainder[31-i];
    end
endmodule
