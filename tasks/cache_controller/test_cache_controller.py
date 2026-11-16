# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Protocol, refill data, and invalidation checks for the default cache."""

import random
from typing import NamedTuple

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge, Timer

WORDS = 256
LINES = 4
MASK = (1 << 32) - 1


class Outputs(NamedTuple):
    inv_ready: int = 0
    cpu_req_ready: int = 0
    cpu_rsp_valid: int = 0
    cpu_rsp_data: int = 0
    mem_req_valid: int = 0
    mem_req_addr: int = 0
    mem_rsp_ready: int = 0


class Model:
    def __init__(self):
        self.entries = {}
        self.miss = None
        self.sent = False
        self.response = None

    def outputs(self, rst, inv):
        if rst:
            return Outputs()
        if self.response is not None:
            return Outputs(cpu_rsp_valid=1, cpu_rsp_data=self.response)
        if self.miss is not None:
            if self.sent:
                return Outputs(mem_rsp_ready=1)
            return Outputs(mem_req_valid=1, mem_req_addr=self.miss // 2)
        return Outputs(inv_ready=1, cpu_req_ready=int(not inv))

    def tick(self, *, rst, inv, addr, take, mem_take, refill):
        before = self.outputs(rst, inv)
        if rst:
            self.__init__()
        elif inv and before.inv_ready:
            self.entries.clear()
        elif addr is not None and before.cpu_req_ready:
            line, offset = divmod(addr, 2)
            entry = self.entries.get(line % LINES)
            if entry is not None and entry[0] == line:
                self.response = entry[1][offset]
            else:
                self.miss = addr
        elif before.mem_req_valid and mem_take:
            self.sent = True
        elif refill is not None and before.mem_rsp_ready:
            line, offset = divmod(self.miss, 2)
            words = (refill & MASK, refill >> 32)
            self.entries[line % LINES] = (line, words)
            self.response = words[offset]
            self.miss = None
            self.sent = False
        elif take and before.cpu_rsp_valid:
            self.response = None


def memory_line(line_addr, version=0):
    low = (0xA0374129 + 0x03121119 * line_addr + 0x12440125 * version) & MASK
    high = low ^ 0x9D37A056
    return high << 32 | low


async def setup(dut):
    dut.rst.value = 1
    dut.inv_valid.value = 0
    dut.cpu_req_valid.value = 0
    dut.cpu_req_addr.value = 0
    dut.cpu_rsp_ready.value = 0
    dut.mem_req_ready.value = 0
    dut.mem_rsp_valid.value = 0
    dut.mem_rsp_data.value = 0
    Clock(dut.clk, 10, unit="ns").start()
    await ClockCycles(dut.clk, 2)
    await FallingEdge(dut.clk)
    return Model()


def check(dut, expected, context):
    for name, exp in zip(Outputs._fields, expected, strict=True):
        value = getattr(dut, name).value
        got = int(value) if value.is_resolvable else str(value)
        assert got == exp, f"{context}: {name}={got}, expected {exp}"


async def cycle(dut, model, *, addr=None, inv=0, take=1, mem_take=0, refill=None, rst=0, tag=""):
    dut.rst.value = rst
    dut.inv_valid.value = inv
    dut.cpu_req_valid.value = int(addr is not None)
    dut.cpu_req_addr.value = addr or 0
    dut.cpu_rsp_ready.value = take
    dut.mem_req_ready.value = mem_take
    dut.mem_rsp_valid.value = int(refill is not None)
    dut.mem_rsp_data.value = refill or 0

    context = (f"{tag} rst={rst} inv={inv} addr={addr} cpu_rsp_ready={take} "
               f"mem_req_ready={mem_take} refill={refill}")
    await Timer(1, unit="ns")
    before = model.outputs(rst, inv)
    check(dut, before, f"{context} before edge")
    model.tick(rst=rst, inv=inv, addr=addr, take=take, mem_take=mem_take, refill=refill)
    await RisingEdge(dut.clk)
    await ReadOnly()
    check(dut, model.outputs(rst, inv), f"{context} after edge")
    await FallingEdge(dut.clk)
    return before


async def miss(dut, model, addr, version=0):
    await cycle(dut, model, addr=addr, tag="request miss")
    before = await cycle(dut, model, mem_take=1, tag="accept line address")
    expect = (1, addr // 2)
    actual = (before.mem_req_valid, before.mem_req_addr)
    assert actual == expect, f"addr={addr}: memory request={actual}, expected {expect}"
    refill = memory_line(addr // 2, version)
    await cycle(dut, model, refill=refill, tag="refill line")
    await cycle(dut, model, tag="consume refill response")


@cocotb.test()
async def test_refill_caches_both_words(dut):
    model = await setup(dut)
    for addr in (0x23, 0x28):
        await miss(dut, model, addr)
        for hit_addr in (addr, addr ^ 1, addr):
            await cycle(dut, model, addr=hit_addr, tag="hit cached word")
            before = await cycle(dut, model, tag="consume hit response")
            expected = (memory_line(hit_addr // 2) >> (32 * (hit_addr % 2))) & MASK
            actual = (before.cpu_rsp_valid, before.cpu_rsp_data)
            expected_response = (1, expected)
            assert actual == expected_response, (
                f"addr={hit_addr}: hit response={actual}, expected {expected_response}"
            )


@cocotb.test()
async def test_conflicting_tags_replace_only_their_index(dut):
    model = await setup(dut)
    await miss(dut, model, 0x14)
    for addr in (0x12, 0x1A, 0x12, 0x62, 0x1A):
        await miss(dut, model, addr)
        await cycle(dut, model, addr=0x15, tag="different index stays resident")
        await cycle(dut, model, tag="consume independent-index hit")


@cocotb.test()
async def test_backpressure_and_early_refill(dut):
    model = await setup(dut)
    addr = 0x87
    refill = memory_line(addr // 2)
    followup = addr ^ 1
    await cycle(dut, model, addr=addr)
    for step in range(4):
        await cycle(dut, model, addr=followup, refill=refill, tag=f"memory request stalled {step}")
    await cycle(dut, model, addr=followup, refill=refill, mem_take=1, tag="memory request accepted")
    await cycle(dut, model, addr=followup, refill=refill, tag="refill accepted on its own edge")
    for step in range(5):
        await cycle(dut, model, addr=followup, take=0, tag=f"CPU response stalled {step}")
    await cycle(dut, model, addr=followup, tag="CPU response drains without request lookahead")
    await cycle(dut, model, addr=followup, tag="pending CPU request now accepted")
    await cycle(dut, model, tag="consume second word")


@cocotb.test()
async def test_invalidate_waits_and_takes_priority(dut):
    model = await setup(dut)
    for addr in (0x40, 0x42, 0x44, 0x46):
        await miss(dut, model, addr)
    await cycle(dut, model, addr=0x47, take=0, tag="old line hit")
    for step in range(3):
        await cycle(dut, model, addr=0x40, inv=1, take=0, tag=f"invalidate waiting {step}")
    await cycle(dut, model, addr=0x40, inv=1, tag="retire old response")
    await cycle(dut, model, addr=0x40, inv=1, tag="invalidate wins over CPU")
    for addr in (0x40, 0x42, 0x44, 0x46):
        await miss(dut, model, addr, version=1)


@cocotb.test()
async def test_reset_cancels_every_pending_phase(dut):
    model = await setup(dut)
    addr = 0x95
    for stage in range(3):
        await miss(dut, model, 0xE2)
        await cycle(dut, model, addr=addr, tag="begin pending miss")
        if stage >= 1:
            await cycle(dut, model, mem_take=1, tag="accept pending memory request")
        if stage >= 2:
            await cycle(dut, model, refill=memory_line(addr // 2), take=0, tag="start pending CPU response")
        await cycle(dut, model, rst=1, addr=addr, inv=1, mem_take=1, tag=f"reset at phase {stage}")
        await miss(dut, model, addr, version=stage + 1)
        await miss(dut, model, 0xE2, version=stage + 1)
        await cycle(dut, model, inv=1, tag="clean slate")


@cocotb.test()
async def test_seeded_mixed_traffic(dut):
    model = await setup(dut)
    rng = random.Random(472019)
    cpu_pending = None
    inv_pending = 0
    mem_pending = None
    mem_delay = 0
    completed = 0
    for step in range(750):
        rst = int(rng.random() < 0.013)
        if rst:
            cpu_pending, inv_pending, mem_pending = None, 0, None
            mem_delay = 0
        if cpu_pending is None and rng.random() < 0.58:
            cpu_pending = rng.choice([0x20, 0x21, 0x28, rng.randrange(WORDS - 1)])
        inv_pending |= int(rng.random() < 0.022)
        refill = mem_pending if mem_delay == 0 else None
        take = int(rng.random() < 0.66)
        mem_take = int(rng.random() < 0.58)
        before = await cycle(dut, model, addr=cpu_pending, inv=inv_pending, take=take,
                             mem_take=mem_take, refill=refill, rst=rst, tag=f"random {step}")
        if before.cpu_req_ready:
            cpu_pending = None
        if before.inv_ready:
            inv_pending = 0
        if before.mem_req_valid and mem_take:
            mem_pending = memory_line(before.mem_req_addr, rng.randrange(8))
            mem_delay = rng.randrange(4)
        elif before.mem_rsp_ready and refill is not None:
            mem_pending = None
        elif mem_delay:
            mem_delay -= 1
        completed += int(before.cpu_rsp_valid and take)
    assert completed >= 55, f"seeded 750-cycle traffic: completed={completed}, expected at least 55"
