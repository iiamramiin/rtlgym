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
