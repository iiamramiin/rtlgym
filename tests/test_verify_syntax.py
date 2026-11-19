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
])
def test_monitor_uses_only_the_task_clock(tmp_path, change):
    result = validate(change(SEQUENTIAL), tmp_path, SEQUENTIAL_PORTS, "clk", "rst")
    assert not result.valid and result.reason


def test_validation_resource_stop_is_inconclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_syntax, "run", lambda *args, **kwargs:
                        tools.ToolRun(False, None, "timeout", 15, timed_out=True))
    result = validate(COMBINATIONAL, tmp_path)
    assert not result.valid and result.inconclusive


def test_unwritten_module_storage_is_left_for_the_formal_gate(tmp_path):
    code = """module rtl_checker(input [3:0] x,input [2:0] count);
/* verilator lint_off UNDRIVEN */
reg enable_check;
always @* if(enable_check) assert(count == x[2:0]);
endmodule
"""
    result = validate(code, tmp_path)
    assert result.valid, result.reason


def test_clocked_blocking_history_need_not_reset(tmp_path):
    code = SEQUENTIAL.replace("expected<=0; seen<=0;", "seen<=0;").replace(
        "expected <= q + {1'b0,en};", "expected = q + {1'b0,en};"
    )
    result = validate(code, tmp_path, SEQUENTIAL_PORTS, "clk", "rst")
    assert result.valid and result.state_bits == 3, result.reason


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


def prove_observer(source, harness, tmp_path, succeeds=True):
    target = tmp_path / "init_formal.sv"
    target.write_text(source + "\n" + harness)
    script = (f'read_verilog -formal -sv "{target}"; prep -top harness -flatten; '
              'memory_map; opt; sat -verify -seq 6 -set-init-zero -prove-asserts')
    proof = tools.run(["yosys", "-p", script], cwd=tmp_path, timeout_s=10)
    assert proof.ok == succeeds, proof.log
    assert ("no model found: SUCCESS" if succeeds else "proof did fail") in proof.log, proof.log


@pytest.mark.parametrize("initial", [0, 1, 9])
@pytest.mark.parametrize("style", ["declaration", "block"])
def test_constant_initialization_survives_simulation_and_formal(tmp_path, initial, style):
    declaration = f"reg [3:0] history = 4'd{initial};" if style == "declaration" else (
        f"reg [3:0] history; initial begin history = 4'd{initial}; end")
    code = f"""module rtl_checker(input clk,en,input [3:0] q);
{declaration}
always @(posedge clk) begin assert(q==history); history<=history+en; end
endmodule
"""
    ports = {"clk": ("input", 1), "en": ("input", 1), "q": ("output", 4)}
    result = validate(code, tmp_path, ports, "clk")
    assert result.valid and result.state_bits == 4, result.reason
    assert "initial begin" in result.source and "initial begin" in result.instrumented
    harness = f"""module harness(input clk,en);
reg [3:0] q = 4'd{initial};
always @(posedge clk) q <= q+en;
rtl_checker observer(.*);
endmodule
"""
    prove_observer(result.source, harness, tmp_path)
    bench = f"""module tb;
reg clk=0,en=1; reg [3:0] q=4'd{initial}; wire __rtlgym_fail;
rtl_checker observer(.*);
always #5 clk=~clk;
always @(posedge clk) q<=q+en;
initial begin
 #61; if(__rtlgym_fail !== 0) $fatal(1,"initial state changed");
 en=0; q=0;
 #10; if(__rtlgym_fail !== 1) $fatal(1,"wrong value missed");
 $display("CHECKED"); $finish;
end
endmodule
"""
    compile_and_run(result.instrumented, bench, tmp_path)
    # Explicit nonzero init must win over SAT's default for unspecified state.
    if initial:
        wrong = harness.replace(f"q = 4'd{initial}", "q = 4'd0")
        prove_observer(result.source, wrong, tmp_path, succeeds=False)


@pytest.mark.parametrize("declaration", [True, False])
def test_complete_array_initialization_is_preserved(tmp_path, declaration):
    init = ("reg [1:0] history[0:3] = '{default:2'd2};" if declaration else
            "reg [1:0] history[0:3]; integer i; "
            "initial begin for(i=0;i<4;i=i+1) history[i]=2; end")
    code = f"""module rtl_checker(input clk,input [1:0] q);
{init}
reg [1:0] index=0;
always @(posedge clk) begin
 assert(q==history[index]); history[index]<=q; index<=index+1'b1;
end
endmodule
"""
    ports = {"clk": ("input", 1), "q": ("output", 2)}
    result = validate(code, tmp_path, ports, "clk")
    assert result.valid and result.state_bits == 10, result.reason
    harness = "module harness(input clk); wire [1:0] q=2; rtl_checker observer(.*); endmodule\n"
    prove_observer(result.source, harness, tmp_path)
    bench = """module tb;
reg clk=0; reg[1:0] q=2; wire __rtlgym_fail; rtl_checker observer(.*);
always #5 clk=~clk;
initial begin
 #51; if(__rtlgym_fail !== 0) $fatal(1,"array init");
 q=0; #10; if(__rtlgym_fail !== 1) $fatal(1,"array mismatch");
 $display("CHECKED"); $finish;
end
endmodule
"""
    compile_and_run(result.instrumented, bench, tmp_path)


@pytest.mark.parametrize("initializer", [
    "initial history=en;",
    "initial if(en) history=0;",
    "initial begin #1; history=0; end",
    "initial history<=0;",
    "initial history=4'bxx01;",
    "initial en=0;",
    "initial history=0; initial history=1;",
])
def test_nonconstant_timed_or_racing_initialization_is_rejected(tmp_path, initializer):
    code = f"""module rtl_checker(input clk,en,input[3:0]q);
reg[3:0]history; {initializer}
always@(posedge clk) begin assert(q==history); history<=q; end
endmodule
"""
    ports = {"clk": ("input", 1), "en": ("input", 1), "q": ("output", 4)}
    result = validate(code, tmp_path, ports, "clk")
    assert not result.valid and result.reason
    assert "initialstatic" not in result.reason and "moddiv" not in result.reason


def test_partial_init_and_partial_reset_are_allowed(tmp_path):
    code = """module rtl_checker(input clk,rst,input[1:0]q);
reg[1:0]history; initial history[0]=0;
always@(posedge clk) begin
 if(rst) history[1]<=0; else begin assert(q==history); history<=q; end
end
endmodule
"""
    result = validate(code, tmp_path, {"clk": ("input", 1), "rst": ("input", 1),
                                     "q": ("output", 2)}, "clk", "rst")
    assert result.valid and result.state_bits == 2, result.reason


def test_same_initial_block_constant_rewrites_and_expressions_are_deterministic(tmp_path):
    code = """module rtl_checker(input clk,input[3:0]q);
localparam [3:0] P=4'h6;
reg[3:0]history;
initial begin history=~P; history[1:0]=2'b11; end
always@(posedge clk) begin assert(q==history); history<=q; end
endmodule
"""
    result = validate(code, tmp_path, {"clk": ("input", 1), "q": ("output", 4)}, "clk")
    assert result.valid, result.reason
    prove_observer(result.source, "module harness(input clk); wire[3:0]q=4'hb; "
                   "rtl_checker observer(.*); endmodule\n", tmp_path)


def test_automatic_function_initializer_runs_for_each_call(tmp_path):
    code = """module rtl_checker(input[3:0]x,input[2:0]count);
function automatic integer pop(input[3:0]bits);
 integer total=0; integer i;
 begin for(i=0;i<4;i=i+1) total=total+bits[i]; pop=total; end
endfunction
always @* assert(count==pop(x));
endmodule
"""
    result = validate(code, tmp_path)
    assert result.valid, result.reason
    bench = """module tb;
reg[3:0]x; reg[2:0]count; wire __rtlgym_fail; rtl_checker observer(.*);
initial begin
 x=15; count=4; #1; if(__rtlgym_fail!==0) $fatal(1,"first call");
 x=1; count=1; #1; if(__rtlgym_fail!==0) $fatal(1,"initializer was lifted");
 x=0; count=0; #1; if(__rtlgym_fail!==0) $fatal(1,"zero call");
 $display("CHECKED"); $finish;
end
endmodule
"""
    compile_and_run(result.instrumented, bench, tmp_path)


def test_counting_helpers_preserve_all_four_state_combinations(tmp_path):
    code = """module rtl_checker(input[3:0]x,input[2:0]count);
always @* begin
 assert(count==$countones(x));
 assert($onehot(x)==(count==1));
 assert($onehot0(x)==(count<=1));
end
endmodule
"""
    result = validate(code, tmp_path)
    assert result.valid and result.assert_count == 3, result.reason
    assert "$countones" not in result.source and "$onehot" not in result.instrumented
    bench = """module tb;
reg[3:0]x; reg[2:0]count; wire __rtlgym_fail;
integer pattern,bitno,value,remaining,ones,j;
rtl_checker observer(.*);
initial begin
 for(pattern=0;pattern<256;pattern=pattern+1) begin
  remaining=pattern; ones=0;
  for(bitno=0;bitno<4;bitno=bitno+1) begin
   value=remaining%4; remaining=remaining/4;
   case(value) 0:x[bitno]=0; 1:begin x[bitno]=1;ones=ones+1;end
    2:x[bitno]=1'bx; 3:x[bitno]=1'bz; endcase
  end
  for(j=0;j<8;j=j+1) begin
   count=j; #1;
   if(__rtlgym_fail !== (j!=ones)) $fatal(1,"helpers x=%b count=%d",x,count);
  end
 end
 $display("CHECKED"); $finish;
end
endmodule
"""
    compile_and_run(result.instrumented, bench, tmp_path)
    harness = """module harness(input[3:0]x);
wire[2:0]count={2'b0,x[0]}+{2'b0,x[1]}+{2'b0,x[2]}+{2'b0,x[3]};
rtl_checker observer(.*);
endmodule
"""
    prove_observer(result.source, harness, tmp_path)


@pytest.mark.parametrize("blocking", [True, False])
def test_initialized_blocking_and_nonblocking_history_preserve_statement_order(tmp_path, blocking):
    operator = "=" if blocking else "<="
    checked = "q+1'b1" if blocking else "q"
    code = f"""module rtl_checker(input clk,input[3:0]q);
reg[3:0]history=9;
always@(posedge clk) begin
 assert(q==history);
 history {operator} history+1'b1;
 assert(history=={checked});
end
endmodule
"""
    ports = {"clk": ("input", 1), "q": ("output", 4)}
    result = validate(code, tmp_path, ports, "clk")
    assert result.valid and result.state_bits == 4, result.reason
    harness = """module harness(input clk); reg[3:0]q=9;
always@(posedge clk)q<=q+1'b1; rtl_checker observer(.*); endmodule
"""
    prove_observer(result.source, harness, tmp_path)
    bench = """module tb;
reg clk=0; reg[3:0]q=9; wire __rtlgym_fail; rtl_checker observer(.*);
always #5 clk=~clk; always@(posedge clk)q<=q+1'b1;
initial begin #61; if(__rtlgym_fail!==0) $fatal(1,"assignment order");
 $display("CHECKED"); $finish; end
endmodule
"""
    compile_and_run(result.instrumented, bench, tmp_path)
    # Run the exact submitted native checker beside the regenerated native code
    # on the same trace, retaining native immediate assertions in each.
    native_bench = bench.replace(" wire __rtlgym_fail;", "").replace(
        'if(__rtlgym_fail!==0) $fatal(1,"assignment order");', '')
    for name, native in (("submitted", code), ("regenerated", result.source)):
        target = tmp_path / f"{name}.sv"
        binary = tmp_path / f"{name}.vvp"
        target.write_text(native + native_bench)
        compiled = tools.run(["iverilog", "-g2012", "-s", "tb", "-o", str(binary), str(target)],
                             cwd=tmp_path, timeout_s=10)
        assert compiled.ok, compiled.log
        simulated = tools.run(["vvp", str(binary)], cwd=tmp_path, timeout_s=10)
        assert simulated.ok and "ERROR" not in simulated.log, simulated.log


def test_path_dependent_module_history_is_classified_as_arbitrary_state(tmp_path):
    code = """module rtl_checker(input clk,en,input[3:0]q);
reg[3:0] scratch;
always@(posedge clk) begin
 if(en) begin scratch=q+1'b1; assert(scratch!=q); end
 else begin scratch=q; assert(scratch==q); end
end
endmodule
"""
    ports = {"clk": ("input", 1), "en": ("input", 1), "q": ("output", 4)}
    result = validate(code, tmp_path, ports, "clk")
    assert result.valid and result.state_bits == 0, result.reason
    bad = code.replace("scratch=q; assert(scratch==q);", "assert(scratch==q);")
    rejected = validate(bad, tmp_path, ports, "clk")
    assert rejected.valid and rejected.state_bits == 4, rejected.reason


@pytest.mark.parametrize("signed", [False, True])
def test_power_of_two_remainder_preserves_native_signed_values(tmp_path, signed):
    sign = "signed" if signed else ""
    code = f"""module rtl_checker(input {sign}[3:0]x,input {sign}[3:0]count);
always @* assert(count==(x%4));
endmodule
"""
    ports = {"x": ("input", 4), "count": ("output", 4)}
    result = validate(code, tmp_path, ports)
    assert result.valid, result.reason
    bench = f"""module tb;
reg {sign}[3:0]x,count; wire __rtlgym_fail; integer i;
rtl_checker observer(.*);
initial begin
 for(i={-8 if signed else 0};i<{8 if signed else 16};i=i+1) begin
  x=i; count=i%4; #1;
  if(__rtlgym_fail!==0) $fatal(1,"remainder x=%d",x);
  count=count+1; #1; if(__rtlgym_fail!==1) $fatal(1,"remainder mismatch");
 end
 $display("CHECKED"); $finish;
end
endmodule
"""
    compile_and_run(result.instrumented, bench, tmp_path)
    harness = f"""module harness(input {sign}[3:0]x);
wire {sign}[3:0]count=x%4; rtl_checker observer(.*); endmodule
"""
    prove_observer(result.source, harness, tmp_path)


@pytest.mark.parametrize("divisor", ["0", "3", "-4", "x"])
def test_remainder_outside_constant_positive_power_of_two_is_rejected(tmp_path, divisor):
    code = f"module rtl_checker(input[3:0]x,input[2:0]count); always @* assert(count==x%{divisor}); endmodule"
    result = validate(code, tmp_path)
    assert not result.valid and result.reason


@pytest.mark.parametrize("reverse", [False, True])
def test_reduced_array_addresses_preserve_high_indices_in_reads_and_writes(tmp_path, reverse):
    initial = ("history[3]=0; for(i=0;i<3;i=i+1) history[i]=3-i;" if reverse else
               "history[0]=0; for(i=0;i<3;i=i+1) history[i+1]=i+1;")
    shift = ("for(i=2;i>=0;i=i-1) history[i+1]=history[i]; history[0]=q;" if reverse else
             "for(i=0;i<3;i=i+1) history[i]=history[i+1]; history[3]=q;")
    head = 3 if reverse else 0
    code = f"""module rtl_checker(input clk,input[1:0]q);
reg[1:0]history[0:3]; integer i;
initial begin {initial} end
always@(posedge clk) begin assert(q==history[{head}]); {shift} end
endmodule
"""
    result = validate(code, tmp_path, {"clk": ("input", 1), "q": ("output", 2)}, "clk")
    assert result.valid and result.state_bits == 8, result.reason
    harness = """module harness(input clk);
reg[1:0]q=0; always@(posedge clk) q<=q+1'b1;
rtl_checker observer(.*); endmodule
"""
    prove_observer(code, harness, tmp_path)
    prove_observer(result.source, harness, tmp_path)
    bench = """module tb;
reg clk=0; reg[1:0]q=0; wire __rtlgym_fail;
rtl_checker observer(.*);
always #5 clk=~clk; always@(posedge clk)q<=q+1'b1;
initial begin #121;
 if(__rtlgym_fail!==0) $fatal(1,"high array index changed");
 $display("CHECKED"); $finish; end
endmodule
"""
    compile_and_run(result.instrumented, bench, tmp_path)
    native_bench = bench.replace(" wire __rtlgym_fail;", "").replace(
        'if(__rtlgym_fail!==0) $fatal(1,"high array index changed");', '')
    for name, native in (("submitted", code), ("regenerated", result.source)):
        target = tmp_path / f"array_{name}.sv"
        binary = tmp_path / f"array_{name}.vvp"
        target.write_text(native + native_bench)
        compiled = tools.run(["iverilog", "-g2012", "-s", "tb", "-o", str(binary), str(target)],
                             cwd=tmp_path, timeout_s=10)
        assert compiled.ok, compiled.log
        simulated = tools.run(["vvp", str(binary)], cwd=tmp_path, timeout_s=10)
        assert simulated.ok and "ERROR" not in simulated.log, simulated.log


@pytest.mark.parametrize("selection", ["index", "index[1:0]"])
def test_array_negative_and_out_of_range_addresses_match_native_source(tmp_path, selection):
    code = f"""module rtl_checker(input signed[3:0]index,input[1:0]count);
reg[1:0]words[0:3]; initial begin words[0]=0; words[1]=1; words[2]=2; words[3]=3; end
always @* assert(count==words[{selection}]);
endmodule
"""
    result = validate(code, tmp_path, {"index": ("input", 4), "count": ("output", 2)})
    assert result.valid, result.reason
    address = "(i&3)" if "[" in selection else "i+4" if "+" in selection else "i"
    bench = f"""module tb;
reg signed[3:0]index; reg[1:0]count; wire __rtlgym_fail;
integer i,address,failures=0;
rtl_checker observer(.*);
initial begin
 for(i=-8;i<8;i=i+1) begin
  index=i; address={address};
  count=(address>=0 && address<4) ? address : 0;
  #1;
  if(__rtlgym_fail !== !(address>=0 && address<4)) $fatal(1,"address changed: i=%d",i);
 end
 $display("CHECKED"); $finish;
end
endmodule
"""
    compile_and_run(result.instrumented, bench, tmp_path)
    native_bench = bench.replace(" wire __rtlgym_fail;", "").replace(
        'if(__rtlgym_fail !== !(address>=0 && address<4)) $fatal(1,"address changed: i=%d",i);', '')
    expected_failures = 0 if "[" in selection else 12
    for name, native in (("submitted", code), ("regenerated", result.source)):
        target = tmp_path / f"bounds_{name}.sv"
        binary = tmp_path / f"bounds_{name}.vvp"
        target.write_text(native + native_bench)
        compiled = tools.run(["iverilog", "-g2012", "-s", "tb", "-o", str(binary), str(target)],
                             cwd=tmp_path, timeout_s=10)
        assert compiled.ok, compiled.log
        simulated = tools.run(["vvp", str(binary)], cwd=tmp_path, timeout_s=10)
        assert simulated.ok and simulated.log.count("ERROR:") == expected_failures, simulated.log


def test_nested_counting_expansion_is_rejected_before_operand_duplication(tmp_path):
    expression = "$countones(" * 8 + "x" + ")" * 8
    code = ("module rtl_checker(input[3:0]x,input[2:0]count); "
            f"always @* assert(count=={expression}); endmodule")
    result = validate(code, tmp_path)
    assert not result.valid and "Expanded checker exceeds" in result.reason


def test_loop_expansion_is_capped_while_accumulating_bodies(tmp_path):
    expression = "$countones($countones($countones(x)))"
    code = f"""module rtl_checker(input[3:0]x,input[2:0]count);
always @* begin for(integer i=0;i<128;i=i+1) assert(count=={expression}); end
endmodule
"""
    result = validate(code, tmp_path)
    assert not result.valid and "Expanded checker exceeds" in result.reason



def test_ambiguously_discarded_array_index_arithmetic_is_rejected(tmp_path):
    code = """module rtl_checker(input signed[3:0]index,input[1:0]count);
reg[1:0]words[0:3]; initial begin words[0]=0; words[1]=1; words[2]=2; words[3]=3; end
always @* assert(count==words[index+4]);
endmodule
"""
    result = validate(code, tmp_path, {"index": ("input", 4), "count": ("output", 2)})
    assert not result.valid and "Array index was reduced ambiguously" in result.reason


def test_two_state_declarations_are_rejected_instead_of_changing_x_coercion(tmp_path):
    code = """module rtl_checker(input[3:0]x,input[2:0]count);
bit value;
always @* begin value=x[0]; assert(count==value); end
endmodule
"""
    result = validate(code, tmp_path)
    assert not result.valid and "Use logic/reg instead of two-state bit variables" in result.reason


def test_function_locals_cannot_reuse_static_history_across_calls(tmp_path):
    code = """module rtl_checker(input[3:0]x,input[2:0]count);
function integer accumulate(input[3:0]bits);
 integer total;
 begin
  if(bits==15) total=0; else total=total+bits;
  accumulate=total;
 end
endfunction
always @* assert(count==accumulate(x));
endmodule
"""
    result = validate(code, tmp_path)
    assert not result.valid and "Function locals must be assigned before use on every call" in result.reason


def test_function_arrays_cannot_hide_static_history(tmp_path):
    code = """module rtl_checker(input[3:0]x,input[2:0]count);
function integer accumulate(input[3:0]bits);
 integer values[0:1];
 begin
  if(bits==15) values[0]=0; else values[0]=values[0]+bits;
  accumulate=values[0];
 end
endfunction
always @* assert(count==accumulate(x));
endmodule
"""
    result = validate(code, tmp_path)
    assert not result.valid and "unpacked function arrays are unsupported" in result.reason
