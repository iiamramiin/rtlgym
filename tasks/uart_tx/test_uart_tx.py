"""Hidden testbench for uart_tx (CLKS_PER_BIT = 4), cycle-accurate."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge

CPB = 4
FRAME = 10 * CPB


async def setup(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.start.value = 0
    dut.data.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 2)
    await FallingEdge(dut.clk)
    dut.rst.value = 0


async def sample(dut):
    """Advance one clock and return (tx, busy) as seen right after the edge."""
    await RisingEdge(dut.clk)
    await ReadOnly()
    out = (int(dut.tx.value), int(dut.busy.value))
    await FallingEdge(dut.clk)
    return out


async def send_and_check(dut, byte, scramble=None):
    """Pulse start for one cycle, then check every cycle of the frame."""
    dut.data.value, dut.start.value = byte, 1
    bits = [0] + [(byte >> i) & 1 for i in range(8)] + [1]
    for k in range(FRAME):
        tx, busy = await sample(dut)
        if k == 0:
            dut.start.value = 0
        if scramble:
            dut.data.value = scramble.getrandbits(8)
            dut.start.value = scramble.getrandbits(1)
        exp = bits[k // CPB]
        assert busy == 1, f"byte 0x{byte:02x} cycle {k}: busy={busy}, expected 1 during the frame"
        assert tx == exp, f"byte 0x{byte:02x} cycle {k} (bit {k // CPB}): tx={tx}, expected {exp}"
    dut.start.value = 0
    tx, busy = await sample(dut)
    assert (tx, busy) == (1, 0), f"byte 0x{byte:02x} end of frame: (tx,busy)=({tx},{busy}), expected (1,0)"


@cocotb.test()
async def test_idle(dut):
    await setup(dut)
    for i in range(10):
        got = await sample(dut)
        assert got == (1, 0), f"idle cycle {i}, no start: (tx,busy)={got}, expected (1, 0)"


@cocotb.test()
async def test_single_byte(dut):
    await setup(dut)
    await send_and_check(dut, 0xA5)


@cocotb.test()
async def test_edge_bytes(dut):
    await setup(dut)
    for b in (0x00, 0xFF, 0x01, 0x80):
        await send_and_check(dut, b)
        await sample(dut)


@cocotb.test()
async def test_inputs_ignored_while_busy(dut):
    await setup(dut)
    await send_and_check(dut, 0x3C, scramble=random.Random(12))


@cocotb.test()
async def test_reset_mid_frame(dut):
    await setup(dut)
    dut.data.value, dut.start.value = 0x00, 1
    await sample(dut)
    dut.start.value = 0
    for _ in range(13):
        await sample(dut)
    dut.rst.value = 1
    got = await sample(dut)
    assert got == (1, 0), f"rst=1 mid-frame: (tx,busy)={got}, expected (1, 0) in the same cycle"
    dut.rst.value = 0
    for i in range(3):
        got = await sample(dut)
        assert got == (1, 0), f"cycle {i} after rst released, no start: (tx,busy)={got}, " \
                              "expected (1, 0)"
    await send_and_check(dut, 0x96)


@cocotb.test()
async def test_random_back_to_back(dut):
    await setup(dut)
    rng = random.Random(13)
    for _ in range(6):
        await send_and_check(dut, rng.getrandbits(8))
