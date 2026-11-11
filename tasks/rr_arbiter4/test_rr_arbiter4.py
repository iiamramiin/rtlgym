"""Hidden testbench for rr_arbiter4."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge


class Model:
    def __init__(self):
        self.last, self.gnt = 3, 0

    def tick(self, rst, req):
        if rst:
            self.last, self.gnt = 3, 0
            return
        self.gnt = 0
        for k in range(1, 5):
            i = (self.last + k) % 4
            if req >> i & 1:
                self.gnt, self.last = 1 << i, i
                return


async def setup(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.req.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 2)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    return Model()


async def drive(dut, m, reqs, rsts=None):
    for n, req in enumerate(reqs):
        rst = rsts[n] if rsts else 0
        dut.req.value, dut.rst.value = req, rst
        await RisingEdge(dut.clk)
        m.tick(rst, req)
        await ReadOnly()
        got = int(dut.gnt.value)
        assert got == m.gnt, f"cycle {n} req={req:04b} rst={rst}: gnt={got:04b}, expected {m.gnt:04b}"
        await FallingEdge(dut.clk)


@cocotb.test()
async def test_no_requests(dut):
    m = await setup(dut)
    await drive(dut, m, [0] * 4)


@cocotb.test()
async def test_single_requester(dut):
    m = await setup(dut)
    await drive(dut, m, [0b0100] * 3 + [0b0001] * 2 + [0b1000] * 2)


@cocotb.test()
async def test_all_requesting_rotates(dut):
    m = await setup(dut)
    await drive(dut, m, [0b1111] * 12)


@cocotb.test()
async def test_skips_idle_and_keeps_pointer(dut):
    m = await setup(dut)
    await drive(dut, m, [0b1010, 0b1010, 0b0000, 0b1011, 0b0110, 0b0000, 0b1111])


@cocotb.test()
async def test_random(dut):
    m = await setup(dut)
    rng = random.Random(11)
    reqs = [rng.getrandbits(4) for _ in range(600)]
    rsts = [int(rng.random() < 0.01) for _ in reqs]
    await drive(dut, m, reqs, rsts)
