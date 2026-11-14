"""Hidden testbench for seq_detect_1011."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge


class Model:
    def __init__(self):
        self.hist = []
        self.match = 0

    def tick(self, rst, din):
        if rst:
            self.hist, self.match = [], 0
            return
        self.hist = (self.hist + [din])[-4:]
        self.match = int(self.hist == [1, 0, 1, 1])


async def setup(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.din.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 2)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    return Model()


async def drive(dut, m, bits, rsts=None):
    matches = 0
    for i, b in enumerate(bits):
        rst = rsts[i] if rsts else 0
        dut.din.value, dut.rst.value = b, rst
        await RisingEdge(dut.clk)
        m.tick(rst, b)
        await ReadOnly()
        got = int(dut.match.value)
        assert got == m.match, f"bit {i} (din={b}, rst={rst}): match={got}, expected {m.match}"
        matches += got
        await FallingEdge(dut.clk)
    return matches


async def check_count(dut, m, bits, expected):
    got = await drive(dut, m, bits)
    stream = "".join(map(str, bits))
    assert got == expected, f"din={stream}: {got} matches, expected {expected}"


@cocotb.test()
async def test_single_match(dut):
    m = await setup(dut)
    await check_count(dut, m, [0, 1, 0, 1, 1, 0, 0], 1)


@cocotb.test()
async def test_overlap(dut):
    m = await setup(dut)
    await check_count(dut, m, [1, 0, 1, 1, 0, 1, 1, 0, 1, 1], 3)


@cocotb.test()
async def test_near_misses(dut):
    m = await setup(dut)
    await check_count(dut, m, [1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0], 0)


@cocotb.test()
async def test_reset_clears_history(dut):
    m = await setup(dut)
    bits = [1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 1]
    rsts = [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0]
    await drive(dut, m, bits, rsts)
    # pattern split across a reset must not match
    await drive(dut, m, [1, 0, 1, 1, 0, 1], [0, 0, 1, 0, 0, 0])


@cocotb.test()
async def test_random(dut):
    m = await setup(dut)
    rng = random.Random(8)
    bits = [rng.getrandbits(1) for _ in range(800)]
    rsts = [int(rng.random() < 0.02) for _ in bits]
    await drive(dut, m, bits, rsts)
