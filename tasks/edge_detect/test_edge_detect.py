"""Hidden testbench for edge_detect."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge


class Model:
    def __init__(self):
        self.prev = self.rise = self.fall = 0

    def tick(self, rst, din):
        if rst:
            self.prev = self.rise = self.fall = 0
        else:
            self.rise = int(din and not self.prev)
            self.fall = int((not din) and self.prev)
            self.prev = din


async def setup(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.din.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 2)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    return Model()


async def drive(dut, m, seq, rst_seq=None):
    for i, din in enumerate(seq):
        rst = rst_seq[i] if rst_seq else 0
        dut.din.value, dut.rst.value = din, rst
        await RisingEdge(dut.clk)
        m.tick(rst, din)
        await ReadOnly()
        got = (int(dut.rise.value), int(dut.fall.value))
        assert got == (m.rise, m.fall), \
            f"cycle {i} din={din} rst={rst}: (rise,fall)={got}, expected {(m.rise, m.fall)}"
        await FallingEdge(dut.clk)


@cocotb.test()
async def test_idle_after_reset(dut):
    m = await setup(dut)
    await drive(dut, m, [0] * 5)


@cocotb.test()
async def test_single_pulse(dut):
    m = await setup(dut)
    await drive(dut, m, [0, 0, 1, 1, 1, 1, 0, 0, 0])


@cocotb.test()
async def test_toggle_every_cycle(dut):
    m = await setup(dut)
    await drive(dut, m, [1, 0] * 8)


@cocotb.test()
async def test_reset_mid_stream(dut):
    m = await setup(dut)
    seq = [1, 1, 1, 0, 1, 1, 0, 0]
    rst = [0, 0, 1, 0, 0, 1, 0, 0]
    await drive(dut, m, seq, rst)


@cocotb.test()
async def test_random(dut):
    m = await setup(dut)
    rng = random.Random(7)
    await drive(dut, m, [rng.getrandbits(1) for _ in range(500)])
