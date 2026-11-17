# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Checker XML validation, regeneration and trusted failure instrumentation."""

import pytest

from rtlgym import tools, verify_syntax

pytestmark = pytest.mark.needs_tools
PORTS = {"x": ("input", 4), "count": ("output", 3)}
COMBINATIONAL = """module rtl_checker(input logic [3:0] x, input logic [2:0] count);
logic [2:0] expected;
always_comb begin
 expected = 0;
 for (integer i=0; i<4; i=i+1) expected = expected + {2'b0,x[i]};
 assert(count == expected);
end
endmodule
"""
SEQUENTIAL = """module rtl_checker(input logic clk,rst,en,input logic [1:0] q);
reg [1:0] expected;
reg seen;
always @(posedge clk) begin
 if(rst) begin expected<=0; seen<=0; end
 else begin
  if(seen) assert(q == expected);
  expected <= q + {1'b0,en};
  seen <= 1;
 end
end
endmodule
"""
SEQUENTIAL_PORTS = {"clk": ("input", 1), "rst": ("input", 1), "en": ("input", 1),
                    "q": ("output", 2)}


def validate(code, tmp_path, ports=PORTS, clock=None, reset=None):
    return verify_syntax.validate_checker(code, ports, tmp_path, clock=clock, reset=reset)


def compile_and_run(source, bench, tmp_path):
    target = tmp_path / "generated.sv"
    target.write_text(source + "\n" + bench)
    binary = tmp_path / "generated.vvp"
    compiled = tools.run(["iverilog", "-g2012", "-s", "tb", "-o", str(binary), str(target)],
                         cwd=tmp_path, timeout_s=10)
    assert compiled.ok, compiled.log
    simulation = tools.run(["vvp", str(binary)], cwd=tmp_path, timeout_s=10)
    assert simulation.ok and "CHECKED" in simulation.log, simulation.log


def test_combinational_checker_generates_real_failure_signal(tmp_path):
    result = validate(COMBINATIONAL, tmp_path)
    assert result.valid, result.reason
    assert result.assert_count == 1 and result.state_bits == 0
    assert "assert (" in result.source and "assert (" not in result.instrumented
    assert "while" not in result.source and "for (" not in result.source
    bench = """module tb;
reg [3:0] x;
reg [2:0] count;
wire __rtlgym_fail;
integer i,j,expected;
rtl_checker observer(.*);
initial begin
 for(i=0;i<16;i=i+1) begin
  x=i; expected=(i&1)+((i>>1)&1)+((i>>2)&1)+((i>>3)&1);
  for(j=0;j<8;j=j+1) begin
   count=j; #1;
   if(__rtlgym_fail !== (j!=expected)) $fatal(1,"x=%d count=%d flag=%b",i,j,__rtlgym_fail);
  end
 end
 x=4'b000x; count=0; #1;
 if(__rtlgym_fail !== 1) $fatal(1,"unknown assertion operand was missed");
 $display("CHECKED"); $finish;
end
endmodule
"""
    compile_and_run(result.instrumented, bench, tmp_path)


def test_pure_function_and_high_loop_indices_preserve_values(tmp_path):
    code = """module rtl_checker(input logic [15:0] x,input logic [4:0] count);
function automatic [4:0] pop(input [15:0] bits);
integer i;
begin
 pop=0;
 for(i=0;i<16;i=i+1) pop=pop+{4'b0,bits[i]};
end
endfunction
always @* assert(count==pop(x));
endmodule
"""
    ports = {"x": ("input", 16), "count": ("output", 5)}
    result = validate(code, tmp_path, ports)
    assert result.valid, result.reason
    bench = """module tb;
reg [15:0] x;
reg [4:0] count;
wire __rtlgym_fail;
integer i;
rtl_checker observer(.*);
initial begin
 for(i=0;i<16;i=i+1) begin
  x=16'b1 << i; count=1; #1;
  if(__rtlgym_fail !== 0) $fatal(1,"single bit %d",i);
 end
 x=16'hffff; count=16; #1;
 if(__rtlgym_fail !== 0) $fatal(1,"all bits");
 count=15; #1;
 if(__rtlgym_fail !== 1) $fatal(1,"missing error");
 $display("CHECKED"); $finish;
end
endmodule
"""
    compile_and_run(result.instrumented, bench, tmp_path)


def test_clocked_failure_sticks_after_sample_edge(tmp_path):
    result = validate(SEQUENTIAL, tmp_path, SEQUENTIAL_PORTS, "clk", "rst")
    assert result.valid, result.reason
    assert result.state_bits == 3
    bench = """module tb;
reg clk=0,rst=1,en=1;
reg [1:0] q=0;
wire __rtlgym_fail;
rtl_checker observer(.*);
always #5 clk=~clk;
initial begin
 #6; if(__rtlgym_fail !== 0) $fatal(1,"reset");
 rst=0;
 #10; q=1;
 #10; if(__rtlgym_fail !== 0) $fatal(1,"correct history");
 q=0;
 #10; if(__rtlgym_fail !== 1) $fatal(1,"wrong counter was missed");
 q=1;
 #10; if(__rtlgym_fail !== 1) $fatal(1,"failure did not stick");
 $display("CHECKED"); $finish;
end
endmodule
"""
    compile_and_run(result.instrumented, bench, tmp_path)


def test_native_source_proves_known_counter(tmp_path):
    result = validate(SEQUENTIAL, tmp_path, SEQUENTIAL_PORTS, "clk", "rst")
    assert result.valid, result.reason
    source = tmp_path / "formal.sv"
    source.write_text(result.source + """
module harness(input clk,rst,en);
reg [1:0] q;
always @(posedge clk) if(rst) q<=0; else if(en) q<=q+1'b1;
rtl_checker observer(.*);
endmodule
""")
    script = (f'read_verilog -formal -sv "{source}"; prep -top harness -flatten; '
              "sat -verify -seq 6 -set-init-zero -prove-asserts -set-at 1 rst 1 "
              "-set-at 2 rst 0 -set-at 3 rst 0 -set-at 4 rst 0 -set-at 5 rst 0 -set-at 6 rst 0")
    proof = tools.run(["yosys", "-p", script], cwd=tmp_path, timeout_s=10)
    assert proof.ok and "no model found: SUCCESS" in proof.log, proof.log


def test_clocked_unknown_assertion_operand_sets_failure(tmp_path):
    result = validate(SEQUENTIAL, tmp_path, SEQUENTIAL_PORTS, "clk", "rst")
    assert result.valid, result.reason
    bench = """module tb;
reg clk=0,rst=1,en=1;
reg [1:0] q=0;
wire __rtlgym_fail;
rtl_checker observer(.*);
always #5 clk=~clk;
initial begin
 #6; rst=0;
 #10; q=2'bx1;
 #10; if(__rtlgym_fail !== 1) $fatal(1,"clocked unknown operand was missed");
 $display("CHECKED"); $finish;
end
endmodule
"""
    compile_and_run(result.instrumented, bench, tmp_path)


def test_constant_failure_remains_a_native_false_alarm(tmp_path):
    code = "module rtl_checker(input [3:0] x,input [2:0] count); always @* assert(1'b0); endmodule\n"
    result = validate(code, tmp_path)
    assert result.valid and result.assert_count == 1, result.reason
    source = tmp_path / "constant_failure.sv"
    source.write_text(result.source)
    script = f'read_verilog -formal -sv "{source}"; prep -top rtl_checker; sat -verify -prove-asserts'
    proof = tools.run(["yosys", "-p", script], cwd=tmp_path, timeout_s=10)
    assert not proof.ok and "proof did fail" in proof.log, proof.log


@pytest.mark.parametrize("case_form", ["casex", "casez", "unique case", "priority case"])
def test_special_case_semantics_are_rejected(tmp_path, case_form):
    code = f"""module rtl_checker(input [3:0] x,input [2:0] count);
always @* begin
 {case_form} (x)
  4'b0000: assert(count == 0);
  default: assert(count != 0);
 endcase
end
endmodule
"""
    result = validate(code, tmp_path)
    assert not result.valid and result.reason


@pytest.mark.parametrize("body", [
    "initial $finish;",
    "initial $display(123);",
    "initial if (0) $finish; always @* assert(count == x[2:0]);",
    "always @* assume(count == 0);",
    "always @* cover(count == 0);",
    "always @* force count = 0;",
    "always @* assert(count == $past(x));",
    "always @* assert(count == $time);",
    "always @* assert(count == $root.hidden.value);",
    "always @* assert(count == 0) else $error(123);",
    "helper u();",
    'import "DPI-C" function int outside(); always @* assert(outside() == 0);',
    "always @* begin while(x != 0) assert(count != 0); end",
])
def test_unsupported_checker_semantics_are_rejected(tmp_path, body):
    code = "module rtl_checker(input [3:0] x,input [2:0] count);\n" + body + "\nendmodule\n"
    result = validate(code, tmp_path)
    assert not result.valid and result.reason


@pytest.mark.parametrize("code", [
    '`include "hidden.sv"\n' + COMBINATIONAL,
    '`define FINISH $finish\n' + COMBINATIONAL,
    COMBINATIONAL + "module another; endmodule\n",
    COMBINATIONAL.replace("input logic [2:0] count", "output logic [2:0] count"),
    COMBINATIONAL.replace("input logic [2:0] count", "input logic [1:0] count"),
    COMBINATIONAL.replace("logic [2:0] expected;", "logic [2:0] __rtlgym_fail;"),
    COMBINATIONAL.replace("expected = 0;", "x = 0; expected = 0;"),
])
def test_namespace_provenance_and_interface_are_checked(tmp_path, code):
    result = validate(code, tmp_path)
    assert not result.valid and result.reason


@pytest.mark.parametrize("change", [
    lambda code: code.replace("posedge clk", "negedge clk"),
    lambda code: code.replace("posedge clk", "posedge en"),
    lambda code: code.replace("expected<=0; seen<=0;", "seen<=0;"),
    lambda code: code.replace("expected<=0;", "if(en) expected<=0;"),
])
def test_monitor_clock_and_complete_reset_are_required(tmp_path, change):
    result = validate(change(SEQUENTIAL), tmp_path, SEQUENTIAL_PORTS, "clk", "rst")
    assert not result.valid and result.reason


def test_validation_resource_stop_is_inconclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_syntax, "run", lambda *args, **kwargs:
                        tools.ToolRun(False, None, "timeout", 15, timed_out=True))
    result = validate(COMBINATIONAL, tmp_path)
    assert not result.valid and result.inconclusive


def test_submitted_tool_pragmas_cannot_hide_undriven_monitor(tmp_path):
    code = """module rtl_checker(input [3:0] x,input [2:0] count);
/* verilator lint_off UNDRIVEN */
reg enable_check;
always @* if(enable_check) assert(count == x[2:0]);
endmodule
"""
    result = validate(code, tmp_path)
    assert not result.valid and result.reason


def test_clocked_blocking_assignment_cannot_create_unreset_history(tmp_path):
    code = SEQUENTIAL.replace("expected<=0; seen<=0;", "seen<=0;").replace(
        "expected <= q + {1'b0,en};", "expected = q + {1'b0,en};"
    )
    result = validate(code, tmp_path, SEQUENTIAL_PORTS, "clk", "rst")
    assert not result.valid and "nonblocking" in result.reason


def test_clocked_local_work_variable_is_allowed_when_assigned_before_use(tmp_path):
    code = SEQUENTIAL.replace("always @(posedge clk) begin", "always @(posedge clk) begin\n reg ok;")
    code = code.replace("if(seen) assert(q == expected);", "ok = q == expected;\n if(seen) assert(ok);")
    result = validate(code, tmp_path, SEQUENTIAL_PORTS, "clk", "rst")
    assert result.valid, result.reason


def test_clocked_local_cannot_reuse_a_previous_edges_temporary(tmp_path):
    code = SEQUENTIAL.replace("always @(posedge clk) begin", "always @(posedge clk) begin\n reg ok;")
    code = code.replace("if(seen) assert(q == expected);",
                        "if(en) ok = q == expected;\n if(seen) assert(ok);")
    result = validate(code, tmp_path, SEQUENTIAL_PORTS, "clk", "rst")
    assert not result.valid and "before use" in result.reason
