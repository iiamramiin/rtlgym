# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Scoreboard for a framed, streaming Internet checksum."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer


def checksum(data):
    total = sum(value << (8 if i % 2 == 0 else 0) for i, value in enumerate(data))
    while total > 0xffff:
        total = (total & 0xffff) + (total >> 16)
    return total ^ 0xffff


class Model:
    def __init__(self):
        self.packet = []
        self.pending = None

    def ready(self, last, ready, rst):
        return not rst and (not last or self.pending is None or ready)

    def edge(self, valid, data, last, ready, rst):
        if rst:
            self.packet.clear()
            self.pending = None
            return
        take = valid and self.ready(last, ready, rst)
        if ready:
            self.pending = None
        if take:
            self.packet.append(data)
            if last:
                self.pending = checksum(self.packet)
                self.packet.clear()


async def start(dut):
    dut.rst.value = 1
    dut.in_valid.value = 0
    dut.in_data.value = 0
    dut.in_last.value = 0
    dut.out_ready.value = 0
    Clock(dut.clk, 10, unit="ns").start()
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    return Model()


def check(dut, model, last, ready, rst, context):
    expected = (str(int(model.ready(last, ready, rst))), str(int(model.pending is not None)),
                f"{(model.pending or 0):016b}")
    got = (str(dut.in_ready.value), str(dut.out_valid.value), str(dut.out_checksum.value))
    assert got == expected, f"{context}: (in_ready,out_valid,checksum)={got}, expected {expected}"


async def cycle(dut, model, *, valid=0, data=0, last=0, ready=1, rst=0, tag=""):
    dut.in_valid.value = valid
    dut.in_data.value = data
    dut.in_last.value = last
    dut.out_ready.value = ready
    dut.rst.value = rst
    context = f"{tag} rst={rst} valid={valid} byte=0x{data:02x} last={last} ready={ready}"
    await Timer(1, unit="ns")
    await ReadOnly()
    check(dut, model, last, ready, rst, context + " before edge")
    took = valid and model.ready(last, ready, rst)
    await RisingEdge(dut.clk)
    model.edge(valid, data, last, ready, rst)
    await ReadOnly()
    check(dut, model, last, ready, rst, context + " after edge")
    await FallingEdge(dut.clk)
    return took


async def packet(dut, model, data):
    for i, value in enumerate(data):
        await cycle(dut, model, valid=1, data=value, last=(i == len(data) - 1), tag=f"byte {i}")


@cocotb.test()
async def test_odd_and_even_packets(dut):
    m = await start(dut)
    for payload in ([0x91], [0x12, 0x34, 0x56], [0x12, 0x34], [0x10, 0xf0, 0x24, 0x08]):
        await packet(dut, m, payload)
    await cycle(dut, m)


@cocotb.test()
async def test_end_around_carry_and_both_zeros(dut):
    m = await start(dut)
    for payload in ([0, 0], [0xff, 0xff], [0xff, 0xff, 1], [0xff, 0xff, 0xff, 0xff],
                    [0xff, 0xaa] * 13):
        await packet(dut, m, payload)
    await cycle(dut, m)


@cocotb.test()
async def test_stall_partial_packet_and_simultaneous_replacement(dut):
    m = await start(dut)
    await cycle(dut, m, valid=1, data=0x37, last=1, ready=0)
    await cycle(dut, m, valid=1, data=0x99, ready=0)
    await cycle(dut, m, valid=1, data=0xa1, ready=0)
    for i in range(4):
        await cycle(dut, m, valid=1, data=0xb7, last=1, ready=0, tag=f"stalled final {i}")
    await cycle(dut, m, valid=1, data=0xb7, last=1, ready=1)
    await cycle(dut, m, ready=0)
    await cycle(dut, m)


@cocotb.test()
async def test_reset_discards_both_packets(dut):
    m = await start(dut)
    await cycle(dut, m, valid=1, data=0x7d, last=1, ready=0)
    await cycle(dut, m, valid=1, data=0x51, ready=0)
    await cycle(dut, m, rst=1, valid=1, data=0x71, last=1, ready=1)
    await packet(dut, m, [0x82])
    await cycle(dut, m)


@cocotb.test()
async def test_seeded_stream(dut):
    m = await start(dut)
    rng = random.Random(731)
    pending = None
    for i in range(900):
        if pending is None and rng.random() < 0.74:
            pending = (rng.getrandbits(8), rng.random() < 0.32)
        rst = rng.random() < 0.018
        value, last = pending or (0, 0)
        took = await cycle(dut, m, valid=pending is not None, data=value, last=last,
                           ready=rng.random() < 0.48, rst=rst, tag=f"random {i}")
        if rst or took:
            pending = None
    if pending is not None:
        await cycle(dut, m, valid=1, data=pending[0], last=pending[1])
    await cycle(dut, m)
