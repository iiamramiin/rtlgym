# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Prove the constant-five mapper against Yosys's native remainder model."""

import shutil
from pathlib import Path

import pytest

from rtlgym import tools

pytestmark = pytest.mark.skipif(shutil.which("yosys") is None, reason="requires Yosys")
MAPPER = Path(__file__).resolve().parents[1] / "rtlgym" / "constant_mod5.v"


def mod_cell(name, a_width, b_width, y_width, signed, divisor):
    return rf"""
    cell $mod \{name}
        parameter \A_SIGNED {signed}
        parameter \B_SIGNED {signed}
        parameter \A_WIDTH {a_width}
        parameter \B_WIDTH {b_width}
        parameter \Y_WIDTH {y_width}
        connect \A \a
        connect \B {divisor}
        connect \Y \{name}_value
    end
"""


def yosys(tmp_path, rtlil, commands):
    source = tmp_path / "proof.il"
    source.write_text(rtlil, encoding="utf-8")
    script = "; ".join((f'read_rtlil "{source}"', *commands))
    result = tools.run(["yosys", "-p", script], cwd=tmp_path, timeout_s=20)
    assert result.ok, result.log
    return result.log


@pytest.mark.parametrize(
    ("a_width", "b_width", "y_width", "signed"),
    [
        (1, 4, 3, 1),     # the only negative value is the most negative value
        (7, 4, 2, 1),     # negative remainder truncated to a narrow output
        (9, 5, 12, 1),    # signed remainder extended to a wide output
        (4, 12, 12, 0),   # unsigned dividend narrower than both other ports
        (10, 3, 2, 0),    # identical bit pattern as a signed negative divisor
        (12, 8, 12, 0),
    ],
)
def test_mapper_matches_native_remainder(tmp_path, a_width, b_width, y_width, signed):
    divisor = f"{b_width}'{5:0{b_width}b}"
    got = mod_cell("mapped", a_width, b_width, y_width, signed, divisor)
    expected = mod_cell("native", a_width, b_width, y_width, signed, divisor)
    rtlil = rf"""
module \proof
    wire width {a_width} input 1 \a
    wire width {y_width} output 2 \mapped_value
    wire width {y_width} output 3 \native_value
    {got}
    {expected}
end
"""
    log = yosys(tmp_path, rtlil, [
        f'techmap -map "{MAPPER}" proof/mapped',
        # Force the replacement to happen; a proof of two native mods would be vacuous.
        "select -assert-none proof/mapped",
        "select -assert-count 1 proof/native",
        "select -assert-count 1 t:$mod",
        "sat -verify -timeout 15 -prove mapped_value native_value -show-inputs -show-outputs proof",
    ])
    assert "no model found: SUCCESS" in log


@pytest.mark.parametrize(
    ("divisor", "b_width", "signed"),
    [
        ("4'0000", 4, 0),                         # zero divisor
        ("4'0111", 4, 0),                         # different constant
        ("3'101", 3, 1),                          # five's bit pattern denotes negative three
        ("4'1011", 4, 1),                         # negative five
        (r"{ 2'01 \dynamic_bit 1'1 }", 4, 0),     # can be five, but is not constant
    ],
)
def test_mapper_leaves_unsupported_divisors_unmodified(tmp_path, divisor, b_width, signed):
    target = mod_cell("target", 8, b_width, 8, signed, divisor)
    rtlil = rf"""
module \proof
    wire width 8 input 1 \a
    wire input 2 \dynamic_bit
    wire width 8 output 3 \target_value
    {target}
end
"""
    yosys(tmp_path, rtlil, [
        f'techmap -map "{MAPPER}" proof/target',
        "select -assert-count 1 proof/target",
        "select -assert-count 1 t:$mod",
    ])
