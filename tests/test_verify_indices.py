# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Native and rendered array indices retain modulo, casts and bounds."""

import pytest

from rtlgym import tools, verify_syntax
from rtlgym.verify_syntax import validate_checker

pytestmark = pytest.mark.needs_tools


def simulate(source, bench, work, stem):
    work.mkdir(parents=True, exist_ok=True)
    target, binary = work / f"{stem}.sv", work / f"{stem}.vvp"
    target.write_text(source + "\n" + bench)
    result = tools.run(["iverilog", "-g2012", "-s", "tb", "-o", str(binary), str(target)], work, 10)
    assert result.ok, result.log
    result = tools.run(["vvp", str(binary)], work, 10)
    assert result.ok and "CHECKED" in result.log, result.log
    return result.log


def prove(source, harness, work, stem):
    target = work / f"{stem}_formal.sv"
    target.write_text(source + "\n" + harness)
    script = (f'read_verilog -formal -sv "{target}"; prep -top harness -flatten; '
              'memory_map; opt; sat -verify -seq 6 -prove-asserts')
    result = tools.run(["yosys", "-p", script], work, 15)
    assert result.ok and "no model found: SUCCESS" in result.log, result.log


@pytest.mark.parametrize("signed", [False, True])
@pytest.mark.parametrize("expression", [
    "ptr % 4", "ptr % 8", "(ptr % 4) + 4", "2'((ptr % 4) + 4)", "4'((ptr + 1) % 4)",
])
def test_modulo_indices_preserve_native_negative_oob_and_explicit_casts(tmp_path, signed, expression):
    sign = "signed" if signed else ""
    source = f"""module rtl_checker(input {sign}[3:0]ptr,input[1:0]count);
reg[1:0]mem[0:3]; initial begin mem[0]=0;mem[1]=1;mem[2]=2;mem[3]=3;end
always @* assert(count==mem[{expression}]);
endmodule
"""
    ports = {"ptr": ("input", 4), "count": ("output", 2)}
    result = validate_checker(source, ports, tmp_path)
    assert result.valid, result.reason
    assert "__rtlgym_index_value" not in result.source
    bench = f"""module tb;
reg {sign}[3:0]ptr; reg[1:0]count; wire __rtlgym_fail; integer i,address;
rtl_checker observer(.*);
initial begin
 for(i=0;i<16;i=i+1) begin
  ptr=i; address={expression}; count=(address>=0 && address<4) ? address : 0; #1;
  if(__rtlgym_fail !== !(address>=0 && address<4)) $fatal(1,"index changed: %d",ptr);
 end
 ptr=4'bxxxx; count=0; #1; if(__rtlgym_fail!==1) $fatal(1,"unknown index");
 ptr=4'bzzzz; #1; if(__rtlgym_fail!==1) $fatal(1,"high impedance index");
 $display("CHECKED"); $finish;
end endmodule
"""
    simulate(result.instrumented, bench, tmp_path, "instrumented")
    native_bench = bench.replace(" wire __rtlgym_fail;", "").replace(
        'if(__rtlgym_fail !== !(address>=0 && address<4)) $fatal(1,"index changed: %d",ptr);', ''
    ).replace('if(__rtlgym_fail!==1) $fatal(1,"unknown index");', '').replace(
        'if(__rtlgym_fail!==1) $fatal(1,"high impedance index");', '')
    original = simulate(source, native_bench, tmp_path, "original")
    wrapped = simulate((tmp_path / "rtl_checker.sv").read_text(), native_bench, tmp_path, "wrapped")
    regenerated = simulate(result.source, native_bench, tmp_path, "regenerated")
    assert original.count("ERROR:") == wrapped.count("ERROR:") == regenerated.count("ERROR:")


@pytest.mark.parametrize("signed", [False, True])
def test_original_and_rendered_modulo_checker_prove_with_native_yosys(tmp_path, signed):
    sign = "signed" if signed else ""
    guard = "if(ptr>=0)" if signed else ""
    source = f"""module rtl_checker(input {sign}[3:0]ptr,input[1:0]count);
reg[1:0]mem[0:3]; initial begin mem[0]=0;mem[1]=1;mem[2]=2;mem[3]=3;end
always @* {guard} assert(count==mem[ptr%4]);
endmodule
"""
    result = validate_checker(source, {"ptr": ("input", 4), "count": ("output", 2)}, tmp_path)
    assert result.valid, result.reason
    harness = f"""module harness(input {sign}[3:0]ptr);
wire[1:0]count=ptr[1:0]; rtl_checker observer(.*); endmodule
"""
    prove(source, harness, tmp_path, "original")
    prove((tmp_path / "rtl_checker.sv").read_text(), harness, tmp_path, "wrapped")
    prove(result.source, harness, tmp_path, "regenerated")


def test_modulo_reads_writes_and_local_loop_scope_preserve_stream_state(tmp_path):
    source = """module rtl_checker(input clk,rst,input[3:0]ptr,input[1:0]count);
reg[1:0]mem[0:3];
initial begin for(integer i=0;i<4;i=i+1) mem[i%4]=i; end
always @(posedge clk) begin
 if(rst) begin for(integer j=0;j<4;j=j+1) mem[j%4]<=j; end
 else begin assert(count==mem[ptr%4]); mem[(ptr+1)%4]<=count; end
end endmodule
"""
    ports = {"clk": ("input", 1), "rst": ("input", 1), "ptr": ("input", 4), "count": ("output", 2)}
    result = validate_checker(source, ports, tmp_path, "clk", "rst")
    assert result.valid, result.reason
    harness = """module harness(input clk,rst,input[3:0]ptr);
reg[1:0]oracle[0:3]; initial begin for(integer i=0;i<4;i=i+1) oracle[i]=i; end
wire[1:0]count=oracle[ptr%4];
always @(posedge clk) begin
 if(rst)begin for(integer i=0;i<4;i=i+1)oracle[i]<=i;end
 else oracle[(ptr+1)%4]<=count;
end
rtl_checker observer(.*); endmodule
"""
    prove(source, harness, tmp_path, "original")
    prove(result.source, harness, tmp_path, "regenerated")
    bench = """module tb;
reg clk=0,rst=1; reg[3:0]ptr=0;reg[1:0]count=0,oracle[0:3];integer i;
wire __rtlgym_fail; rtl_checker observer(.*);
initial begin
 for(i=0;i<4;i=i+1)oracle[i]=i;
 #1;clk=1;#1;clk=0;rst=0;
 for(i=0;i<24;i=i+1)begin
  ptr=i;count=oracle[i%4];#1;clk=1;#1;oracle[(i+1)%4]=count;clk=0;#1;
  if(__rtlgym_fail!==0)$fatal(1,"read or write index changed");
 end
 $display("CHECKED");$finish;
end endmodule
"""
    simulate(result.instrumented, bench, tmp_path, "instrumented")


def test_modulo_index_keeps_function_argument_scope(tmp_path):
    source = """module rtl_checker(input[3:0]ptr,input[1:0]count);
reg[1:0]mem[0:3]; initial begin mem[0]=0;mem[1]=1;mem[2]=2;mem[3]=3;end
function automatic [1:0]lookup(input[3:0]ptr);
 lookup=mem[ptr%4];
endfunction
always @* assert(count==lookup(ptr)); endmodule
"""
    result = validate_checker(source, {"ptr": ("input", 4), "count": ("output", 2)}, tmp_path)
    assert result.valid, result.reason
    harness = """module harness(input[3:0]ptr);
wire[1:0]count=ptr[1:0];rtl_checker observer(.*);endmodule
"""
    prove(source, harness, tmp_path, "original")
    prove(result.source, harness, tmp_path, "regenerated")


@pytest.mark.parametrize("divisor", ["3", "0", "-4"])
def test_invalid_modulo_divisors_remain_rejected_in_array_context(tmp_path, divisor):
    source = f"""module rtl_checker(input signed[3:0]ptr,input[1:0]count);
reg[1:0]mem[0:3]; initial begin mem[0]=0;mem[1]=1;mem[2]=2;mem[3]=3;end
always @* assert(count==mem[ptr%({divisor})]);endmodule
"""
    result = validate_checker(source, {"ptr": ("input", 4), "count": ("output", 2)}, tmp_path)
    assert not result.valid and result.reason


@pytest.mark.parametrize("escaped", [False, True])
def test_helper_name_cannot_be_supplied_by_a_checker(tmp_path, escaped):
    source = """module rtl_checker(input[3:0]ptr,input[1:0]count);
function automatic [1:0]__rtlgym_index_value(input[3:0]x);
 __rtlgym_index_value=x[1:0];endfunction
always @* assert(count==__rtlgym_index_value(ptr));endmodule
"""
    if escaped:
        source = source.replace("__rtlgym_index_value", chr(92) + "__rtlgym_index_value ")
    result = validate_checker(source, {"ptr": ("input", 4), "count": ("output", 2)}, tmp_path)
    assert not result.valid and "Reserved" in result.reason


@pytest.mark.parametrize("expression", [
    "({256'b0,ptr})%4", "({256'b1,4'b0}%4)+(256'b1<<256)",
])
def test_index_width_is_checked_before_trusted_helper_truncation(tmp_path, expression):
    source = f"""module rtl_checker(input[3:0]ptr,input[1:0]count);
reg[1:0]mem[0:3]; initial begin mem[0]=0;mem[1]=1;mem[2]=2;mem[3]=3;end
always @* assert(count==mem[{expression}]);endmodule
"""
    result = validate_checker(source, {"ptr": ("input", 4), "count": ("output", 2)}, tmp_path)
    assert not result.valid and "256 bits" in result.reason


def test_nested_modulo_indices_preserve_both_original_scopes(tmp_path):
    source = """module rtl_checker(input[3:0]ptr,input[1:0]count);
reg[1:0]mem[0:3];initial begin mem[0]=0;mem[1]=1;mem[2]=2;mem[3]=3;end
always @* assert(count==mem[mem[ptr%4]%4]);endmodule
"""
    result = validate_checker(source, {"ptr": ("input", 4), "count": ("output", 2)}, tmp_path)
    assert result.valid, result.reason
    harness = """module harness(input[3:0]ptr);
wire[1:0]count=ptr[1:0];rtl_checker observer(.*);endmodule
"""
    prove(source, harness, tmp_path, "original")
    prove((tmp_path / "rtl_checker.sv").read_text(), harness, tmp_path, "wrapped")
    prove(result.source, harness, tmp_path, "regenerated")


def test_signed_multiplication_is_preserved_in_modulo_index(tmp_path):
    source = """module rtl_checker(input signed[3:0]ptr,input[1:0]count);
reg[1:0]mem[0:3]; initial begin mem[0]=0;mem[1]=1;mem[2]=2;mem[3]=3;end
always @* if(ptr>=0)assert(count==mem[(ptr*3)%4]);endmodule
"""
    result = validate_checker(source, {"ptr": ("input", 4), "count": ("output", 2)}, tmp_path)
    assert result.valid, result.reason
    harness = """module harness(input signed[3:0]ptr);
wire[1:0]count=(ptr*3)%4;rtl_checker observer(.*);endmodule
"""
    prove(source, harness, tmp_path, "original")
    prove(result.source, harness, tmp_path, "regenerated")


def test_both_native_parses_share_the_published_fifteen_second_budget(tmp_path, monkeypatch):
    import time

    native = verify_syntax._native_document
    budgets, elapsed = [], []

    def observed(code, source, xml, workdir, budget_s=15):
        started = time.monotonic()
        budgets.append(budget_s)
        document = native(code, source, xml, workdir, budget_s)
        elapsed.append(time.monotonic() - started)
        return document

    monkeypatch.setattr(verify_syntax, "_native_document", observed)
    source = """module rtl_checker(input[3:0]ptr,input[1:0]count);
reg[1:0]mem[0:3];initial begin mem[0]=0;mem[1]=1;mem[2]=2;mem[3]=3;end
always @* assert(count==mem[ptr%4]);endmodule
"""
    result = validate_checker(source, {"ptr": ("input", 4), "count": ("output", 2)}, tmp_path)
    assert result.valid, result.reason
    assert len(budgets) == 2 and budgets[0] == 15
    assert 0 < budgets[1] <= 15 - elapsed[0] + 0.001


def test_deep_native_array_nesting_is_rejected_without_aborting_validation(tmp_path):
    expression = "mem[" * 1100 + "ptr%4" + "]" * 1100
    source = f"""module rtl_checker(input[3:0]ptr,input[1:0]count);
reg[1:0]mem[0:3]; initial begin mem[0]=0;mem[1]=1;mem[2]=2;mem[3]=3;end
always @* assert(count=={expression});endmodule
"""
    result = validate_checker(source, {"ptr": ("input", 4), "count": ("output", 2)}, tmp_path)
    assert not result.valid and not result.inconclusive
    assert "nesting" in result.reason.lower()
