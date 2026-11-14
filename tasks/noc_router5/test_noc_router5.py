"""Cycle-accurate checks for the five-port XY router at its default parameters."""

import random
from collections import deque

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge, Timer

N, S, E, W, L = range(5)
ALL_READY = 0b11111
IDLE = (None,) * 5
FLIT_BITS = 12


def flit(x, y, payload):
    return (x << 10) | (y << 8) | payload


def output_port(word):
    x, y = word >> 10, (word >> 8) & 3
    if x != 1:
        return E if x > 1 else W
    if y != 1:
        return N if y > 1 else S
    return L


def pack(words):
    return sum((word or 0) << (i * FLIT_BITS) for i, word in enumerate(words))


class Model:
    def __init__(self):
        self.slots = [None] * 5
        self.priority = [deque(range(5)) for _ in range(5)]

    def outputs(self):
        valid = sum(1 << port for port, entry in enumerate(self.slots) if entry is not None)
        return valid, pack([entry[1] if entry is not None else 0 for entry in self.slots])

    def tick(self, inputs, ready, rst):
        if rst:
            self.slots = [None] * 5
            self.priority = [deque(range(5)) for _ in range(5)]
            return 0

        accepted = 0
        for port, entry in enumerate(self.slots):
            priority = self.priority[port]
            if entry is not None:
                if not ready & (1 << port):
                    continue
                while priority[0] != entry[0]:
                    priority.rotate(-1)
                priority.rotate(-1)
                self.slots[port] = None
            for source in priority:
                word = inputs[source]
                if word is not None and output_port(word) == port:
                    accepted |= 1 << source
                    self.slots[port] = (source, word)
                    break
        return accepted


async def setup(dut):
    dut.in_valid.value = 0
    dut.in_flit.value = 0
    dut.out_ready.value = 0
    dut.rst.value = 1
    Clock(dut.clk, 10, unit="ns").start()
    await ClockCycles(dut.clk, 2)
    await FallingEdge(dut.clk)
    return Model()


def check(signal, expected, context):
    value = signal.value
    got = int(value) if value.is_resolvable else str(value)
    assert got == expected, f"{context}: {signal._name}={got}, expected {expected}"


async def cycle(dut, model, inputs=IDLE, ready=ALL_READY, rst=0, tag=""):
    valids = sum(1 << i for i, word in enumerate(inputs) if word is not None)
    dut.in_valid.value = valids
    dut.in_flit.value = pack(inputs)
    dut.out_ready.value = ready
    dut.rst.value = rst
    words = [None if word is None else f"{word:03x}" for word in inputs]
    context = f"{tag} rst={rst} in_valid={valids:05b} flits={words} out_ready={ready:05b}"

    await Timer(1, unit="ns")
    before_valid, before_flit = model.outputs()
    check(dut.out_valid, before_valid, f"{context} before edge")
    check(dut.out_flit, before_flit, f"{context} before edge")
    accepted = model.tick(inputs, ready, rst)
    check(dut.in_ready, accepted, f"{context} before edge")

    await RisingEdge(dut.clk)
    await ReadOnly()
    after_valid, after_flit = model.outputs()
    check(dut.out_valid, after_valid, f"{context} after edge")
    check(dut.out_flit, after_flit, f"{context} after edge")
    await FallingEdge(dut.clk)
    return accepted


@cocotb.test()
async def test_independent_outputs_and_xy_order(dut):
    model = await setup(dut)
    # Simultaneously request N, S, E, W, L. Both destination dimensions differ on E/W.
    words = (flit(1, 2, 0x51), flit(1, 0, 0x32), flit(3, 0, 0x83), flit(0, 2, 0xC4), flit(1, 1, 0x15))
    await cycle(dut, model, words, tag="five different outputs")
    await cycle(dut, model, tag="drain in parallel")
    await cycle(dut, model, tag="idle")


@cocotb.test()
async def test_stall_and_replace(dut):
    model = await setup(dut)
    blocked_east = ALL_READY & ~(1 << E)
    await cycle(dut, model, (None, None, None, flit(2, 1, 0x45), None), ready=blocked_east)
    # East is blocked. The north source cannot enter, but E can send to L.
    waiting = (flit(2, 1, 0x60), None, flit(1, 1, 0x27), None, None)
    await cycle(dut, model, waiting, ready=blocked_east, tag="independent local transfer")
    waiting = (waiting[N], None, None, None, flit(2, 1, 0x94))
    for step in range(3):
        await cycle(dut, model, waiting, ready=blocked_east, tag=f"hold {step}")
    # W is retiring, so L wins over N even though N has waited longer.
    await cycle(dut, model, waiting, tag="replace from successor")
    await cycle(dut, model, (waiting[N], None, None, None, None), tag="wrap to north")
    await cycle(dut, model, tag="drain last word")


@cocotb.test()
async def test_round_robin_wrap_and_idle(dut):
    model = await setup(dut)
    pending = [flit(1, 1, 0x20 + src) for src in range(5)]
    for step in range(12):
        accepted = await cycle(dut, model, pending, tag=f"round {step}")
        for src in range(5):
            if accepted & (1 << src):
                pending[src] = flit(1, 1, 0x40 + 5*step + src)
    for step in range(5):
        accepted = await cycle(dut, model, pending, tag=f"flush requester {step}")
        pending = [word if not accepted & (1 << src) else None for src, word in enumerate(pending)]
    await cycle(dut, model, tag="local drain")
    await cycle(dut, model, tag="idle preserves cursor")
    await cycle(dut, model, (None, None, None, flit(1, 1, 0xBD), None), tag="move cursor to local")
    await cycle(dut, model, tag="retire west")
    await cycle(dut, model, tag="hold cursor during another gap")
    words = (flit(1, 1, 0x47), None, None, None, flit(1, 1, 0x68))
    await cycle(dut, model, words, tag="local wins after idle")
    await cycle(dut, model, (words[N], None, None, None, None), tag="north was still pending")
    await cycle(dut, model, tag="drain")


@cocotb.test()
async def test_reset_discards_resident_flits(dut):
    model = await setup(dut)
    await cycle(dut, model, (None, flit(1, 1, 0x86), flit(1, 2, 0x31), None, None), ready=0)
    await cycle(dut, model, (flit(2, 1, 0x95), None, None, None, None), rst=1, tag="reset while occupied")
    words = (flit(2, 1, 0x95), None, flit(2, 1, 0x99), None, None)
    await cycle(dut, model, words, tag="first post-reset transfer")
    await cycle(dut, model, (None, None, words[E], None, None), tag="second post-reset transfer")
    await cycle(dut, model, tag="drain")


@cocotb.test()
async def test_seeded_traffic(dut):
    model = await setup(dut)
    rng = random.Random(9185)
    pending = list(IDLE)
    # Exercise all compass regions and local delivery. A separate exhaustive-input check
    # complements this traffic profile, which leaves one local injection corner unsampled.
    coordinates = [(x, y) for x in range(4) for y in range(4)]
    local_coordinates = [xy for xy in coordinates if xy != (0, 3)]
    for step in range(600):
        for src in range(5):
            if pending[src] is None and rng.random() < 0.68:
                xy = rng.choice(local_coordinates if src == L else coordinates)
                pending[src] = flit(*xy, rng.getrandbits(8))
        ready = rng.getrandbits(5)
        accepted = await cycle(dut, model, pending, ready, tag=f"random {step}")
        pending = [word if not accepted & (1 << src) else None for src, word in enumerate(pending)]
    for step in range(6):
        accepted = await cycle(dut, model, pending, tag=f"drain {step}")
        pending = [word if not accepted & (1 << src) else None for src, word in enumerate(pending)]
