# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Independent-clock timing and ordered data checks for the default FIFO."""

import random
from collections import deque

import cocotb
from cocotb.triggers import ReadOnly, Timer

DEPTH = 8
MODULUS = 2 * DEPTH


class Model:
    def __init__(self):
        self.words = deque()
        self.wr_position = 0
        self.rd_position = 0
        self.rd_history = (0, 0)
        self.wr_history = (0, 0)
        self.full = 0
        self.empty = 1
        self.data = 0

    def tick(self, *, wr_edge, rd_edge, rst, wr_en, rd_en, din, context):
        if rst:
            self.words.clear()
        push = bool(wr_edge and not rst and wr_en and not self.full)
        pop = bool(rd_edge and not rst and rd_en and not self.empty)
        old_wr, old_rd = self.wr_position, self.rd_position

        if pop:
            assert self.words, f"{context}: occupancy={len(self.words)}, expected at least 1 on a read"
            self.data = self.words.popleft()
        if push:
            self.words.append(din)
        assert len(self.words) <= DEPTH, f"{context}: occupancy={len(self.words)}, expected at most {DEPTH}"

        if wr_edge:
            if rst:
                self.wr_position, self.full, self.rd_history = 0, 0, (0, 0)
            else:
                self.wr_position = (old_wr + push) % MODULUS
                self.full = int((self.wr_position - self.rd_history[1]) % MODULUS == DEPTH)
                self.rd_history = (old_rd, self.rd_history[0])
        if rd_edge:
            if rst:
                self.rd_position, self.empty, self.data, self.wr_history = 0, 1, 0, (0, 0)
            else:
                self.rd_position = (old_rd + pop) % MODULUS
                self.empty = int(self.rd_position == self.wr_history[1])
                self.wr_history = (old_wr, self.wr_history[0])
        return push, pop


class Rig:
    """Schedule both clocks on a single timeline, including simultaneous edges."""

    def __init__(self, dut, *, wr_half, rd_half, wr_phase, rd_phase):
        self.dut = dut
        self.model = Model()
        self.signals = (dut.wr_clk, dut.rd_clk)
        self.levels = [0, 0]
        self.edges = [0, 0]
        self.reset_seen = [False, False]
        self.next_ps = [1000 * wr_phase, 1000 * rd_phase]
        self.half_ps = [1000 * wr_half, 1000 * rd_half]
        self.now_ps = 0
        self.transfers = [0, 0]
        self.coincident_rises = 0
        for signal in self.signals:
            signal.value = 0
        self.drive(rst=1)

    def drive(self, *, wr_en=0, rd_en=0, din=0, rst=0):
        self.rst, self.wr_en, self.rd_en, self.din = rst, wr_en, rd_en, din
        self.dut.rst.value = rst
        self.dut.wr_en.value = wr_en
        self.dut.rd_en.value = rd_en
        self.dut.din.value = din

    @property
    def context(self):
        return (f"t={self.now_ps}ps rst={self.rst} wr_en={self.wr_en} rd_en={self.rd_en} "
                f"din=0x{self.din:02x} clk={self.levels}")

    async def step(self, tag=""):
        at = min(self.next_ps)
        await Timer(at - self.now_ps, unit="ps")
        self.now_ps = at
        rising = [False, False]
        for i, signal in enumerate(self.signals):
            if self.next_ps[i] == at:
                self.levels[i] ^= 1
                signal.value = self.levels[i]
                self.next_ps[i] += self.half_ps[i]
                if self.levels[i] == 1:
                    rising[i] = True
                    self.edges[i] += 1
                    self.reset_seen[i] |= bool(self.rst)
        self.coincident_rises += int(all(rising))
        context = f"{tag} {self.context}"
        push, pop = self.model.tick(wr_edge=rising[0], rd_edge=rising[1], rst=self.rst,
                                    wr_en=self.wr_en, rd_en=self.rd_en, din=self.din, context=context)
        self.transfers[0] += push
        self.transfers[1] += pop

        await ReadOnly()
        if self.reset_seen[0]:
            check(self.dut.full, self.model.full, "full", context)
        if self.reset_seen[1]:
            check(self.dut.empty, self.model.empty, "empty", context)
            check(self.dut.dout, self.model.data, "dout", context)
        # Return in a writable phase before the earliest possible next edge.
        await Timer(1, unit="ps")
        self.now_ps += 1

    async def wait_edges(self, domain, count=1, tag=""):
        target = self.edges[domain] + count
        while self.edges[domain] < target:
            await self.step(tag)

    async def reset(self):
        self.drive(rst=1)
        targets = [count + 2 for count in self.edges]
        while any(have < want for have, want in zip(self.edges, targets, strict=True)):
            await self.step("reset")
        self.drive()


def check(signal, expected, name, context):
    value = signal.value
    actual = int(value) if value.is_resolvable else str(value)
    assert actual == expected, f"{context}: {name}={actual}, expected {expected}"


async def start(dut, *, wr_half=4, rd_half=7, wr_phase=3, rd_phase=1):
    rig = Rig(dut, wr_half=wr_half, rd_half=rd_half, wr_phase=wr_phase, rd_phase=rd_phase)
    await rig.reset()
    return rig


async def enqueue(rig, words):
    for word in words:
        rig.drive(wr_en=1, din=word)
        await rig.wait_edges(0, tag="enqueue")
    rig.drive()


@cocotb.test()
async def test_reset_flushes_and_clears_output(dut):
    rig = await start(dut, wr_half=6, rd_half=4, wr_phase=1, rd_phase=3)
    await enqueue(rig, [0x45, 0x72, 0x8B, 0xFA])
    await rig.wait_edges(1, 3, "publish writes")
    rig.drive(rd_en=1)
    await rig.wait_edges(1, tag="read nonzero word before reset")
    actual = rig.model.data
    assert actual == 0x45, f"{rig.context}: pre-reset data={actual}, expected 69"
    await rig.reset()
    rig.drive(rd_en=1)
    await rig.wait_edges(1, 5, "old words absent after reset")
    await enqueue(rig, [0x61, 0xA8])
    await rig.wait_edges(1, 3, "publish post-reset writes")
    rig.drive(rd_en=1)
    await rig.wait_edges(1, 3, "read new words and underflow")
    actual = rig.model.data
    assert actual == 0xA8, f"{rig.context}: post-reset data={actual}, expected 168"


@cocotb.test()
async def test_full_releases_after_read_synchronizes(dut):
    rig = await start(dut, wr_half=7, rd_half=3)
    await enqueue(rig, range(0x30, 0x30 + DEPTH))
    rig.drive(wr_en=1, din=0xEE)
    await rig.wait_edges(0, 3, "blocked extra writes")
    rig.drive(rd_en=1)
    await rig.wait_edges(1, tag="free precisely one slot")
    rig.drive()
    await rig.wait_edges(0, 2, "full stays high during both synchronization edges")
    actual = rig.model.full
    assert actual == 1, f"{rig.context}: full after two edges={actual}, expected 1"
    await rig.wait_edges(0, tag="full clears on registered flag edge")
    actual = rig.model.full
    assert actual == 0, f"{rig.context}: full after three edges={actual}, expected 0"
    await enqueue(rig, [0xC6])
    rig.drive(rd_en=1)
    await rig.wait_edges(1, DEPTH + 6, "drain oldest-to-newest after slot reuse")


@cocotb.test()
async def test_empty_releases_after_write_synchronizes(dut):
    rig = await start(dut, wr_half=5, rd_half=8)
    await enqueue(rig, [0x9D])
    rig.drive(rd_en=1)
    await rig.wait_edges(1, 2, "empty stays high during both synchronization edges")
    actual = rig.model.empty
    assert actual == 1, f"{rig.context}: empty after two edges={actual}, expected 1"
    await rig.wait_edges(1, tag="empty clears on registered flag edge")
    actual = rig.model.empty
    assert actual == 0, f"{rig.context}: empty after three edges={actual}, expected 0"
    await rig.wait_edges(1, 5, "read one word, then hold on repeated underflow")


@cocotb.test()
async def test_wraparound_with_coincident_edges(dut):
    rig = await start(dut, wr_half=3, rd_half=5, wr_phase=1, rd_phase=1)
    for burst in range(5):
        await enqueue(rig, range(16 * burst, 16 * burst + DEPTH))
        await rig.wait_edges(1, 3, "publish full burst")
        rig.drive(rd_en=1)
        await rig.wait_edges(1, DEPTH + 1, "drain complete burst")
        rig.drive()
        await rig.wait_edges(0, 3, "publish freed space")
    actual = (*rig.transfers, bool(rig.coincident_rises))
    expect = (5 * DEPTH, 5 * DEPTH, True)
    assert actual == expect, f"{rig.context}: writes, reads, coincident edges={actual}, expected {expect}"


@cocotb.test()
async def test_seeded_independent_clock_traffic(dut):
    rng = random.Random(402117)
    for run in range(4):
        fast = rng.randint(2, 5)
        slow = rng.randint(6, 11)
        wr_half, rd_half = (fast, slow) if run % 2 == 0 else (slow, fast)
        wr_phase, rd_phase = rng.randint(1, 13), rng.randint(1, 13)
        profile = f"profile {run} half-periods=({wr_half},{rd_half}) phases=({wr_phase},{rd_phase})"
        rig = await start(dut, wr_half=wr_half, rd_half=rd_half, wr_phase=wr_phase, rd_phase=rd_phase)
        for edge in range(700):
            rig.drive(wr_en=rng.random() < 0.69, rd_en=rng.random() < 0.74, din=rng.randrange(256))
            await rig.step(f"{profile} event {edge}")
        rig.drive(rd_en=1)
        await rig.wait_edges(1, DEPTH + 5, f"{profile} final drain")
        actual = rig.transfers[0] - rig.transfers[1]
        assert actual == 0, f"{profile} {rig.context}: writes minus reads={actual}, expected 0"
        actual = rig.transfers[0]
        assert actual >= 20, f"{profile} {rig.context}: traffic transferred={actual}, expected at least 20"
