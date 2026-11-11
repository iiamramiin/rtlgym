"""Hidden testbench for alu8."""
import random

import cocotb
from cocotb.triggers import Timer


def s8(v):
    return v - 256 if v & 0x80 else v


def model(a, b, op):
    carry = 0
    if op == 0:
        t = a + b
        y, carry = t & 0xFF, t >> 8
    elif op == 1:
        y, carry = (a - b) & 0xFF, int(a < b)
    elif op == 2:
        y = a & b
    elif op == 3:
        y = a | b
    elif op == 4:
        y = a ^ b
    elif op == 5:
        y = int(s8(a) < s8(b))
    elif op == 6:
        y = (a << (b & 7)) & 0xFF
    else:
        y = a >> (b & 7)
    return y, int(y == 0), carry


async def check(dut, a, b, op):
    dut.a.value, dut.b.value, dut.op.value = a, b, op
    await Timer(1, unit="ns")
    y, z, c = model(a, b, op)
    got = (int(dut.y.value), int(dut.zero.value), int(dut.carry.value))
    assert got == (y, z, c), \
        f"op={op:03b} a=0x{a:02x} b=0x{b:02x}: (y,zero,carry)={got}, expected {(y, z, c)}"


def vectors(rng, n):
    edge = [0x00, 0x01, 0x7F, 0x80, 0xFF]
    for a in edge:
        for b in edge:
            yield a, b
    for _ in range(n):
        yield rng.getrandbits(8), rng.getrandbits(8)


@cocotb.test()
async def test_add_sub(dut):
    rng = random.Random(2)
    for a, b in vectors(rng, 200):
        for op in (0, 1):
            await check(dut, a, b, op)


@cocotb.test()
async def test_logic(dut):
    rng = random.Random(3)
    for a, b in vectors(rng, 100):
        for op in (2, 3, 4):
            await check(dut, a, b, op)


@cocotb.test()
async def test_slt(dut):
    rng = random.Random(4)
    for a, b in vectors(rng, 200):
        await check(dut, a, b, 5)


@cocotb.test()
async def test_shifts(dut):
    rng = random.Random(5)
    for a, b in vectors(rng, 100):
        for op in (6, 7):
            await check(dut, a, b, op)


@cocotb.test()
async def test_zero_flag(dut):
    for op in range(8):
        await check(dut, 0, 0, op)
    await check(dut, 0x55, 0x55, 1)
    await check(dut, 0x80, 0x80, 0)
    await check(dut, 0xF0, 0x0F, 2)
