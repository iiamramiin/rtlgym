"""Hidden testbench for fifo_sync (W=8, DEPTH=8)."""
import random
from collections import deque

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge

DEPTH = 8


class Model:
    def __init__(self):
        self.q = deque()
        self.dout = None

    def tick(self, rst, wr, din, rd):
        if rst:
            self.q.clear()
            self.dout = None
            return False
        do_wr = wr and len(self.q) < DEPTH
        do_rd = rd and len(self.q) > 0
        if do_rd:
            self.dout = self.q.popleft()
        if do_wr:
            self.q.append(din)
        return do_rd


async def setup(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.wr_en.value = 0
    dut.rd_en.value = 0
    dut.din.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 2)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    return Model()


async def cycle(dut, m, wr=0, din=0, rd=0, rst=0, tag=""):
    dut.wr_en.value, dut.din.value, dut.rd_en.value, dut.rst.value = wr, din, rd, rst
    await RisingEdge(dut.clk)
    m.tick(rst, wr, din, rd)
    await ReadOnly()
    n = len(m.q)
    got = (int(dut.count.value), int(dut.full.value), int(dut.empty.value))
    exp = (n, int(n == DEPTH), int(n == 0))
    assert got == exp, f"{tag} wr={wr} rd={rd} rst={rst}: (count,full,empty)={got}, expected {exp}"
    if m.dout is not None:
        d = int(dut.dout.value)
        assert d == m.dout, f"{tag} wr={wr} rd={rd}: dout=0x{d:02x}, expected 0x{m.dout:02x}"
    await FallingEdge(dut.clk)


@cocotb.test()
async def test_reset_state(dut):
    m = await setup(dut)
    await cycle(dut, m, tag="idle")
    assert int(dut.empty.value) == 1 and int(dut.full.value) == 0


@cocotb.test()
async def test_fill_and_drain(dut):
    m = await setup(dut)
    for i in range(DEPTH):
        await cycle(dut, m, wr=1, din=0x10 + i, tag=f"fill{i}")
    for i in range(DEPTH):
        await cycle(dut, m, rd=1, tag=f"drain{i}")


@cocotb.test()
async def test_overflow_and_underflow_ignored(dut):
    m = await setup(dut)
    for i in range(DEPTH + 3):
        await cycle(dut, m, wr=1, din=0xA0 + i, tag=f"over{i}")
    await cycle(dut, m, wr=1, din=0xEE, rd=1, tag="full_rw")
    for i in range(DEPTH + 3):
        await cycle(dut, m, rd=1, tag=f"under{i}")
    await cycle(dut, m, wr=1, din=0x5C, rd=1, tag="empty_rw")
    await cycle(dut, m, rd=1, tag="read_back")


@cocotb.test()
async def test_simultaneous_rw(dut):
    m = await setup(dut)
    for i in range(3):
        await cycle(dut, m, wr=1, din=i + 1, tag="prefill")
    for i in range(20):
        await cycle(dut, m, wr=1, din=0x30 + i, rd=1, tag=f"rw{i}")


@cocotb.test()
async def test_pointer_wraparound(dut):
    m = await setup(dut)
    rng = random.Random(9)
    for rnd in range(5):
        for i in range(DEPTH - 1):
            await cycle(dut, m, wr=1, din=rng.getrandbits(8), tag=f"r{rnd}w{i}")
        for i in range(DEPTH - 1):
            await cycle(dut, m, rd=1, tag=f"r{rnd}r{i}")


@cocotb.test()
async def test_random(dut):
    m = await setup(dut)
    rng = random.Random(10)
    for i in range(1500):
        await cycle(dut, m, wr=int(rng.random() < 0.55), din=rng.getrandbits(8),
                    rd=int(rng.random() < 0.5), rst=int(rng.random() < 0.005), tag=f"#{i}")
