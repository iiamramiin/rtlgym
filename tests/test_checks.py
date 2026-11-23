import hashlib
import json
from collections import defaultdict
from pathlib import Path

import pytest

from rtlgym.checks import extract_code, static_check
from rtlgym.task import load_task

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


def test_extract_helper_in_bare_text_outside_the_fences():
    reply = "Helper:\n" + HELPER + "\nTop level:\n" + fence(A_USES_HELPER)
    code = extract_code(reply, "a")
    assert code.startswith(A_USES_HELPER) and HELPER in code and "Helper:" not in code


def test_extract_one_line_module_keeps_what_it_instantiates():
    one_line = "module a(input x, output y); inv u0(.i(x), .o(y)); endmodule"
    reply = fence(HELPER) + "\n" + fence(one_line)
    code = extract_code(reply, "a")
    assert code.startswith(one_line) and HELPER in code


def test_extract_non_code_fence_with_a_bare_module():
    reply = "Compile it with:\n```bash\niverilog -g2012 a.sv\n```\nThe design:\n" + A + \
        "\nThanks!"
    assert extract_code(reply, "a").strip() == A          # no prose, no shell command


def test_extract_top_in_bare_text_wins_over_an_unrelated_fenced_module():
    reply = fence(TB) + "\nAnd the design:\n" + A
    assert extract_code(reply, "a").strip() == A


def test_extract_ignores_modules_only_mentioned_in_comments():
    top = "module a(input x, output y);\n  // unlike tb, this is synthesizable\n  assign y = x;\nendmodule"
    reply = fence(top) + "\nTestbench:\n" + fence("module tb; initial $finish; endmodule")
    code = extract_code(reply, "a")
    assert code.strip() == top and "// unlike tb" in code      # comment kept in the code
    assert static_check(code, "a").ok


@pytest.mark.parametrize("body,uses_helper", [
    ("inv u0(.i(x), .o(y));", True),
    ("inv #(.W(1)) u0 (.i(x), .o(y));", True),
    ("inv u[1:0] (.i(x), .o(y));", True),
    ("/* inv u0(.i(x), .o(y)); */ assign y = x;", False),
    ('initial $display("inv u0(...)"); assign y = x;', False),
    ("wire inv_n; assign inv_n = x; assign y = inv_n;", False),
])
def test_extract_follows_real_instantiations_only(body, uses_helper):
    top = f"module a(input x, output y);\n  {body}\nendmodule"
    code = extract_code(fence(HELPER) + "\n" + fence(top), "a")
    assert ("module inv" in code) == uses_helper


def test_extract_cut_off_reply_returns_only_the_unclosed_code():
    partial = "module a(input x, output y);\n  assign y ="
    reply = "Here is my design, explained step by step.\n\n```verilog\n" + partial
    assert extract_code(reply, "a") == partial + "\n"         # no prose for the compiler
    # Without a fence, or with a fence that has no module, nothing changes.
    assert extract_code("I cannot do that.", "a") == "I cannot do that.\n"
    assert extract_code("See:\n```bash\nls -l", "a").startswith("See:")


def test_extract_closed_fence_returns_partial_top_without_prose():
    partial = "module a(input x, output y);\n  assign y = x;"
    reply = f"Here is my design.\n{fence(partial)}\nThe explanation follows."
    assert extract_code(reply, "a") == partial + "\n"


def test_extract_bare_partial_module_is_unchanged():
    partial = "module a(input x, output y);\n  assign y = x;\n"
    assert extract_code(partial, "a") == partial


def test_extract_closed_partial_fence_uses_the_last_matching_top():
    partial = "module a(input x, output y);\n  assign y = x;"
    reply = f"Draft:\n{fence('module other;')}\nFinal:\n~~~sv\n{partial}\n~~~\nDone."
    assert extract_code(reply, "a") == partial + "\n"
    assert extract_code(reply, "missing") == reply + "\n"


def test_extract_saved_archive_attempts():
    # These incomplete closed-fence sources are the only new extraction changes.
    expected = {
        "mul_pipe3": {"42a2786b7a82", "81c61765113d", "8f649efb8343", "fa4f1c2a25e3"},
        "noc_router5": {"0e8d6e9bcb0b", "1d150c434b40", "73c17611a1c4", "d6ba0ac625d3"},
        "uart_tx": {"535fbb74d625", "61ecc2063f0a", "80ebed69e4a6", "a5cd1c9e1fdb", "e21e51fe8a0f"},
    }
    # The generic extractor already normalizes these checker replies at the base.
    # Verification grading uses extract_checker, so preserve the existing behavior.
    existing_checker_changes = {"1745ccd6d9dc", "02d664dff1a2", "f6183c8e3711"}
    archives = (
        "claude/2026-11-14/claude-haiku-5-5__full.json",
        "claude/2026-11-14/claude-haiku-5-5__none.json",
        "claude/2026-11-14/claude-sonnet-5-5__full.json",
        "claude/2026-11-14/claude-sonnet-5-5__none.json",
        "claude/2026-11-16/repair-pilot/claude-haiku-5-5__full.json",
        "claude/2026-11-16/repair-pilot/claude-haiku-5-5__none.json",
        "claude/2026-11-16/repair-pilot/claude-sonnet-5-5__full.json",
        "claude/2026-11-16/repair-pilot/claude-sonnet-5-5__none.json",
        "claude/2026-11-16/run-a/claude-haiku-5-5__full.json",
        "claude/2026-11-16/run-a/claude-haiku-5-5__none.json",
        "claude/2026-11-16/run-a/claude-sonnet-5-5__full.json",
        "claude/2026-11-16/run-a/claude-sonnet-5-5__none.json",
        "claude/2026-11-16/run-b/claude-haiku-5-5__full.json",
        "claude/2026-11-16/run-b/claude-haiku-5-5__none.json",
        "claude/2026-11-16/run-b/claude-sonnet-5-5__full.json",
        "claude/2026-11-16/run-b/claude-sonnet-5-5__none.json",
        "claude/2026-11-17/verify-pilot/claude-haiku-5-5__full.json",
        "claude/2026-11-17/verify-pilot/claude-sonnet-5-5__full.json",
        "claude/2026-11-19/verify-hard-pilot/claude-haiku-5-5__full.json",
        "claude/2026-11-19/verify-hard-pilot/claude-sonnet-5-5__full.json",
        "ollama/2026-11-22/open-models-smoke/initial-16k/llama3.1_8b.json",
        "ollama/2026-11-22/open-models-smoke/probe/llama3.1_8b.json",
        "ollama/2026-11-22/open-models-smoke/probe/qwen3_14b.json",
        "ollama/2026-11-22/open-models-smoke/smoke/llama3.1_8b__full.json",
        "ollama/2026-11-22/open-models-smoke/smoke/llama3.1_8b__none.json",
        "ollama/2026-11-22/open-models-smoke/smoke/qwen3_14b__full.json",
        "ollama/2026-11-22/open-models-smoke/smoke/qwen3_14b__none.json",
        "ollama/2026-11-22/paper1-llama3.1_8b/llama3.1_8b__full.json",
        "ollama/2026-11-22/paper1-llama3.1_8b/llama3.1_8b__none.json",
    )
    results_root = Path(__file__).resolve().parents[1] / "results"
    changed = defaultdict(set)
    checker_changes = set()
    changed_rows = 0
    for archive in archives:
        data = json.loads((results_root / archive).read_bytes())
        for episode in data["episodes"]:
            task = load_task(episode["task"])
            for attempt in episode.get("trajectory", []):
                saved = attempt.get("code")
                if not isinstance(saved, str):
                    continue
                extracted = extract_code(saved, task.top)
                if extracted == saved:
                    continue
                digest = hashlib.sha256(saved.encode()).hexdigest()[:12]
                if task.kind == "verify":
                    assert digest in existing_checker_changes
                    checker_changes.add(digest)
                    continue
                assert digest in expected.get(task.id, set()), (archive, task.id, digest)
                assert static_check(extracted, task.top).ok
                assert "endmodule" not in extracted
                assert "```" not in extracted and "~~~" not in extracted
                assert attempt["score"] == 0 and not attempt["solved"]
                changed[task.id].add(digest)
                changed_rows += 1
    assert changed_rows == 16  # Shared first submissions occur in both paired arms.
    assert dict(changed) == expected
    assert checker_changes == existing_checker_changes
