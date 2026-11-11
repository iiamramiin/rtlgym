"""Hidden testbench for popcount16. The agent never sees this file."""
import random

import cocotb
from cocotb.triggers import Timer


async def check(dut, x):
    dut.x.value = x
    await Timer(1, unit="ns")
    got = int(dut.count.value)
    exp = bin(x).count("1")
    assert got == exp, f"x=0x{x:04x}: count={got}, expected {exp}"


@cocotb.test()
async def test_extremes(dut):
    for x in (0x0000, 0xFFFF, 0x8000, 0x0001, 0xAAAA, 0x5555):
        await check(dut, x)


@cocotb.test()
async def test_single_bits(dut):
    for i in range(16):
        await check(dut, 1 << i)
        await check(dut, 0xFFFF ^ (1 << i))


@cocotb.test()
async def test_random(dut):
    rng = random.Random(1)
    for _ in range(500):
        await check(dut, rng.getrandbits(16))
