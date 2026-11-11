"""Hidden testbench for up_down_counter."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge


async def setup(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.en.value = 0
    dut.up.value = 1
    dut.load.value = 0
    dut.d.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 2)
    await FallingEdge(dut.clk)
    dut.rst.value = 0


class Model:
    def __init__(self):
        self.q = 0

    def tick(self, rst, en, up, load, d):
        if rst:
            self.q = 0
        elif load:
            self.q = d
        elif en:
            self.q = (self.q + (1 if up else -1)) & 0xFF


async def cycle(dut, m, rst=0, en=0, up=1, load=0, d=0):
    dut.rst.value, dut.en.value, dut.up.value = rst, en, up
    dut.load.value, dut.d.value = load, d
    await RisingEdge(dut.clk)
    m.tick(rst, en, up, load, d)
    await ReadOnly()
    got = int(dut.q.value)
    assert got == m.q, f"rst={rst} en={en} up={up} load={load} d={d}: q={got}, expected {m.q}"
    await FallingEdge(dut.clk)


@cocotb.test()
async def test_reset(dut):
    await setup(dut)
    m = Model()
    for _ in range(5):
        await cycle(dut, m, en=1, up=1)
    await cycle(dut, m, rst=1, en=1, load=1, d=0x5A)
    await cycle(dut, m)


@cocotb.test()
async def test_count_up_wrap(dut):
    await setup(dut)
    m = Model()
    await cycle(dut, m, load=1, d=0xFC)
    for _ in range(8):
        await cycle(dut, m, en=1, up=1)


@cocotb.test()
async def test_count_down_wrap(dut):
    await setup(dut)
    m = Model()
    await cycle(dut, m, load=1, d=0x03)
    for _ in range(8):
        await cycle(dut, m, en=1, up=0)


@cocotb.test()
async def test_load_priority_and_hold(dut):
    await setup(dut)
    m = Model()
    await cycle(dut, m, en=1, up=1, load=1, d=0x40)
    await cycle(dut, m, en=1, up=0, load=1, d=0x41)
    for _ in range(3):
        await cycle(dut, m, en=0, up=1)


@cocotb.test()
async def test_random(dut):
    await setup(dut)
    m = Model()
    rng = random.Random(6)
    for _ in range(400):
        await cycle(dut, m, rst=int(rng.random() < 0.03), en=rng.getrandbits(1),
                    up=rng.getrandbits(1), load=int(rng.random() < 0.1), d=rng.getrandbits(8))
