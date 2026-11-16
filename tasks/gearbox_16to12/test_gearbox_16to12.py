# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""A nibble-queue model and cycle-level handshake checks."""

import random
from collections import deque

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer


class Model:
    def __init__(self):
        self.units = deque()

    def outputs(self, ready, rst):
        valid = len(self.units) >= 3
        sent = valid and ready
        get = not rst and len(self.units) - 3 * sent <= 4
        data = sum(unit << (4 * i) for i, unit in enumerate(list(self.units)[:3])) if valid else 0
        return (int(get), int(valid), data)

    def tick(self, valid, data, ready, rst):
        if rst:
            self.units.clear()
            return
        get, send, _ = self.outputs(ready, rst)
        if send and ready:
            for _ in range(3):
                self.units.popleft()
        if get and valid:
            self.units.extend((data >> i) & 15 for i in range(0, 16, 4))


async def setup(dut):
    dut.rst.value = 1
    dut.in_valid.value = 0
    dut.in_data.value = 0
    dut.out_ready.value = 0
    Clock(dut.clk, 10, unit="ns").start()
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    return Model()


def check(dut, model, ready, rst, context):
    got = (
        str(dut.in_ready.value), str(dut.out_valid.value), str(dut.out_data.value),
    )
    ir, ov, word = model.outputs(ready, rst)
    expected = (str(ir), str(ov), f"{word:012b}")
    assert got == expected, (
        f"{context} occupancy={len(model.units)}: (in_ready,out_valid,out_data)={got}, "
        f"expected {expected}"
    )


async def tick(dut, model, valid=0, data=0, ready=1, rst=0, label=""):
    dut.in_valid.value = valid
    dut.in_data.value = data
    dut.out_ready.value = ready
    dut.rst.value = rst
    context = f"{label} rst={rst} valid={valid} data=0x{data:04x} ready={ready}"
    await Timer(1, unit="ns")
    await ReadOnly()
    check(dut, model, ready, rst, context + " pre-edge")
    accepted = model.outputs(ready, rst)[0] and valid
    await RisingEdge(dut.clk)
    model.tick(valid, data, ready, rst)
    await ReadOnly()
    check(dut, model, ready, rst, context + " post-edge")
    await FallingEdge(dut.clk)
    return accepted


@cocotb.test()
async def test_stream_order_and_residues(dut):
    m = await setup(dut)
    for i, data in enumerate((0x3210, 0x7654, 0xba98, 0xfedc, 0x4321, 0x8765)):
        while not await tick(dut, m, valid=1, data=data, label=f"word {i}"):
            pass
    for i in range(5):
        await tick(dut, m, label=f"drain {i}")


@cocotb.test()
async def test_full_buffer_and_stalled_output(dut):
    m = await setup(dut)
    await tick(dut, m, valid=1, data=0xa589, ready=0)
    await tick(dut, m, valid=1, data=0x6312, ready=0)
    for i in range(8):
        await tick(dut, m, valid=1, data=0x1248, ready=0, label=f"stall {i}")
    await tick(dut, m, valid=1, data=0x1248, ready=1)
    await tick(dut, m, valid=1, data=0x1248, ready=1)
    for i in range(4):
        await tick(dut, m, label=f"drain {i}")


@cocotb.test()
async def test_same_edge_room(dut):
    m = await setup(dut)
    for i in range(16):
        while not await tick(dut, m, valid=1, data=0x0b71 + i, label=f"continuous {i}"):
            pass
    for i in range(5):
        await tick(dut, m, label=f"drain {i}")


@cocotb.test()
async def test_midstream_reset(dut):
    m = await setup(dut)
    await tick(dut, m, valid=1, data=0xffff, ready=0)
    await tick(dut, m, valid=1, data=0xa0b0, ready=0)
    await tick(dut, m, valid=1, data=0x869b, ready=1, rst=1)
    await tick(dut, m, valid=1, data=0x3c2d)
    await tick(dut, m)


@cocotb.test()
async def test_seeded_traffic(dut):
    m = await setup(dut)
    rng = random.Random(71)
    pending = None
    for i in range(640):
        if pending is None and rng.random() < 0.73:
            pending = rng.getrandbits(16)
        rst = rng.random() < 0.017
        accepted = await tick(dut, m, valid=pending is not None, data=pending or 0,
                              ready=rng.random() < 0.62, rst=rst, label=f"random {i}")
        if rst or accepted:
            pending = None
    for i in range(5):
        await tick(dut, m, label=f"drain {i}")
