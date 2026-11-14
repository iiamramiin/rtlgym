module crc32_stream (
    input  logic        clk,
    input  logic        rst,
    input  logic        start,
    input  logic        in_valid,
    input  logic [7:0]  data,
    output logic        out_valid,
    output logic [31:0] crc
);
    logic [31:0] remainder;
    logic restart_byte;

    assign restart_byte = start && data != 8'h00;

    function automatic logic [31:0] update_byte(
        input logic [31:0] initial_remainder,
        input logic [7:0] byte_data
    );
        logic [31:0] value;
        logic feedback;
        begin
            value = initial_remainder;
            for (int i = 0; i < 8; i++) begin
                feedback = value[0] ^ byte_data[i];
                value = (value >> 1) ^ (feedback ? 32'hEDB8_8320 : 32'd0);
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
                remainder <= update_byte(restart_byte ? 32'hFFFF_FFFF : remainder, data);
            end else if (start) begin
                remainder <= '1;
            end
        end
    end

    assign crc = ~remainder;
endmodule
