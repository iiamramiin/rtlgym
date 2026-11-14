import pytest

from rtlgym.checks import extract_code, static_check

GOOD = "module foo(input logic a, output logic y); assign y = a; endmodule\n"


def test_clean_module_passes():
    assert static_check(GOOD, "foo").ok


def test_missing_top_module():
    r = static_check(GOOD, "bar")
    assert not r.ok and "no module named 'bar'" in r.violations[0]


def test_forbidden_system_tasks():
    for bad in ("initial $finish;", "initial $stop;", "initial $system(\"rm -rf /\");",
                "initial $readmemh(\"secret.hex\", m);", "`include \"tb.sv\""):
        r = static_check(GOOD.replace("endmodule", bad + "\nendmodule"), "foo")
        assert not r.ok, bad


def test_forbidden_text_in_comments_is_ignored():
    code = GOOD.replace("endmodule", "// do not call $finish here\n/* $stop */\nendmodule")
    assert static_check(code, "foo").ok


def test_oversized_source_rejected():
    assert not static_check(GOOD + "//" + "x" * 70000, "foo").ok


def test_extract_code_prefers_last_fenced_module():
    reply = ("Here is a draft:\n```verilog\nmodule old; endmodule\n```\n"
             "Fixed version:\n```systemverilog\nmodule foo; endmodule\n```\nDone.")
    assert extract_code(reply).strip() == "module foo; endmodule"


def test_extract_code_without_fence_returns_text():
    assert extract_code(GOOD).strip() == GOOD.strip()


# ------------------------------------------------- shared extraction (all agents)
A = "module a(input x, output y);\n  assign y = x;\nendmodule"
HELPER = "module inv(input i, output o);\n  assign o = ~i;\nendmodule"
A_USES_HELPER = "module a(input x, output y);\n  inv u0(.i(x), .o(y));\nendmodule"
TB = "module tb;\n  a dut(.x(1'b0), .y());\n  initial $finish;\nendmodule"


def fence(code, tag="systemverilog", mark="```"):
    return f"{mark}{tag}\n{code}\n{mark}"


@pytest.mark.parametrize("reply", [
    fence(A), fence(A, "verilog"), fence(A, "sv"), fence(A, ""), fence(A, "verilog", "~~~"),
    "Sure! Here is the design:\n\n" + fence(A) + "\n\nIt assigns y = x.",
    A,
    "The module is below.\n" + A + "\nThis should pass the tests.",
    "```verilog\n" + A + "\n",                         # unclosed fence (reply cut off)
    "Draft:\n" + fence(A.replace("x;", "1'b0;")) + "\nFixed:\n```verilog\n" + A,
])
def test_extract_finds_the_module(reply):
    assert extract_code(reply, "a").strip() == A


def test_extract_unclosed_fence_after_closed_ones():
    reply = fence("module old; endmodule") + "\nNow the real one:\n```verilog\n" + A
    assert extract_code(reply, "a").strip() == A


def test_extract_prefers_the_top_module_over_a_later_testbench():
    reply = fence(A) + "\nAnd a testbench:\n" + fence(TB)
    assert extract_code(reply, "a").strip() == A           # tb (with $finish) left out
    assert extract_code(reply).strip().startswith("module tb")  # no top: last block


def test_extract_several_fences_uses_last_version_of_top():
    v1, v2 = A.replace("x;", "~x;"), A
    reply = fence(v1) + "\nOops, corrected:\n" + fence(v2)
    assert extract_code(reply, "a").strip() == v2


def test_extract_keeps_helper_modules_from_other_fences():
    reply = fence(HELPER) + "\nTop level:\n" + fence(A_USES_HELPER)
    code = extract_code(reply, "a")
    assert A_USES_HELPER in code and HELPER in code


def test_extract_uses_the_last_version_of_a_helper():
    new_helper = HELPER.replace("~i", "!i")
    reply = fence(A_USES_HELPER + "\n\n" + HELPER) + "\nBetter helper:\n" + fence(new_helper)
    code = extract_code(reply, "a")
    assert new_helper in code and HELPER not in code and code.count("module inv") == 1


def test_extract_bare_modules_drop_prose_and_unused_modules():
    reply = "Helper first:\n" + HELPER + "\nThen the top:\n" + A_USES_HELPER + \
        "\nAnd a test:\n" + TB + "\nDone."
    code = extract_code(reply, "a")
    assert code.strip() == HELPER + "\n\n" + A_USES_HELPER


def test_extract_keeps_preamble_in_the_block():
    code = "`timescale 1ns/1ps\n" + A
    assert extract_code(fence(code), "a").strip() == code


def test_extract_reply_with_no_module_is_returned_as_is():
    reply = "I cannot do that."
    assert extract_code(reply, "a") == reply + "\n"
    r = static_check(extract_code(reply, "a"), "a")
    assert not r.ok and "no module named 'a'" in r.violations[0]


def test_extract_ignores_the_word_module_in_prose():
    reply = "The module a below is combinational.\n" + A
    assert extract_code(reply, "a").strip() == A
