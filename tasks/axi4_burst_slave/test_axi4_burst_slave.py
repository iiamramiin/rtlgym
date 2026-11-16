# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Cycle-level AXI channel and memory checks."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge, Timer

OKAY, SLVERR, INCR = 0, 2, 1
MEMORY_BYTES = 256

DEFAULTS = {
    "awid": 0, "awaddr": 0, "awlen": 0, "awsize": 2, "awburst": INCR,
    "awlock": 0, "awcache": 0, "awprot": 0, "awqos": 0, "awregion": 0, "awvalid": 0,
    "wdata": 0, "wstrb": 0, "wlast": 0, "wvalid": 0, "bready": 0,
    "arid": 0, "araddr": 0, "arlen": 0, "arsize": 2, "arburst": INCR,
    "arlock": 0, "arcache": 0, "arprot": 0, "arqos": 0, "arregion": 0, "arvalid": 0,
    "rready": 0,
}


class MemorySlave:
    def __init__(self):
        self.memory = bytearray(MEMORY_BYTES)
        self.write = None
        self.read = None
        self.bvalid, self.bid, self.bresp = 0, 0, OKAY
        self.rvalid, self.rid, self.rresp, self.rdata, self.rlast = 0, 0, OKAY, 0, 0

    def outputs(self, rst):
        return {
            "awready": int(not rst and self.write is None and not self.bvalid),
            "wready": int(not rst and self.write is not None),
            "arready": int(not rst and not self.rvalid),
            "bvalid": self.bvalid,
            "bid": self.bid,
            "bresp": self.bresp,
            "rvalid": self.rvalid,
            "rid": self.rid,
            "rresp": self.rresp,
            "rdata": self.rdata,
            "rlast": self.rlast,
        }

    @staticmethod
    def descriptor(inputs, channel):
        address = inputs[f"{channel}addr"]
        transaction_id = inputs[f"{channel}id"]
        beats = inputs[f"{channel}len"] + 1
        end = address + 4 * beats
        valid = (
            address % 4 == 0 and end <= MEMORY_BYTES and inputs[f"{channel}size"] == 2
            and inputs[f"{channel}burst"] == INCR and not inputs[f"{channel}lock"]
        )
        return address, transaction_id, beats, valid

    def load_read_beat(self):
        address, self.rid, beats, valid = self.read
        self.rvalid = 1
        self.rresp = OKAY if valid else SLVERR
        self.rdata = int.from_bytes(self.memory[address:address + 4], "little") if valid else 0
        self.rlast = int(beats == 1)

    def tick(self, rst, inputs):
        if rst:
            self.__init__()
            return
        before = self.outputs(0)
        if inputs["arvalid"] and before["arready"]:
            self.read = self.descriptor(inputs, "ar")
            self.load_read_beat()
        elif self.rvalid and inputs["rready"]:
            if self.rlast:
                self.rvalid = 0
                self.read = None
            else:
                address, tx_id, beats, valid = self.read
                self.read = address + 4, tx_id, beats - 1, valid
                self.load_read_beat()
        if self.bvalid and inputs["bready"]:
            self.bvalid = 0
        if inputs["awvalid"] and before["awready"]:
            self.write = (*self.descriptor(inputs, "aw"), False)
        elif inputs["wvalid"] and before["wready"]:
            address, tx_id, beats, valid, framing_error = self.write
            if valid:
                for lane in range(4):
                    if inputs["wstrb"] & (1 << lane):
                        self.memory[address + lane] = (inputs["wdata"] >> (8 * lane)) & 0xFF
            framing_error |= bool(inputs["wlast"]) != (beats == 1)
            if beats == 1:
                self.bvalid, self.bid = 1, tx_id
                self.bresp = OKAY if valid and not framing_error else SLVERR
                self.write = None
            else:
                self.write = address + 4, tx_id, beats - 1, valid, framing_error


async def setup(dut):
    dut.rst.value = 1
    for signal, value in DEFAULTS.items():
        getattr(dut, f"s_axi_{signal}").value = value
    Clock(dut.clk, 10, unit="ns").start()
    await ClockCycles(dut.clk, 2)
    await FallingEdge(dut.clk)
    return MemorySlave()


def check_outputs(dut, expected, inputs, rst, label):
    for name, exp in expected.items():
        value = getattr(dut, f"s_axi_{name}").value
        try:
            got = int(value)
        except ValueError:
            got = str(value)
        if got != exp:
            # List active and changed inputs compactly enough for the feedback cap.
            active = " ".join(f"{port}={v:#x}" for port, v in inputs.items() if v != DEFAULTS[port])
            assert got == exp, f"{label} rst={rst} [{active}]: {name}={got}, expected {exp:#x}"


async def cycle(dut, model, label="", rst=0, **updates):
    inputs = {**DEFAULTS, **updates}
    dut.rst.value = rst
    for signal, value in inputs.items():
        getattr(dut, f"s_axi_{signal}").value = value
    await Timer(1, unit="ns")
    await ReadOnly()
    check_outputs(dut, model.outputs(rst), inputs, rst, f"{label} before edge")
    await RisingEdge(dut.clk)
    model.tick(rst, inputs)
    await ReadOnly()
    check_outputs(dut, model.outputs(rst), inputs, rst, f"{label} after edge")
    await FallingEdge(dut.clk)


def request(channel, addr, beats, tx=0, size=2, burst=INCR, lock=0):
    return {
        f"{channel}valid": 1, f"{channel}id": tx, f"{channel}addr": addr,
        f"{channel}len": beats - 1, f"{channel}size": size,
        f"{channel}burst": burst, f"{channel}lock": lock,
    }


def beat(data, strobe=15, last=True):
    return {"wvalid": 1, "wdata": data, "wstrb": strobe, "wlast": int(last)}


async def write_burst(dut, model, address, payloads, strobes=None, flags=None, **attrs):
    beats = len(payloads)
    await cycle(dut, model, "AW", **request("aw", address, beats, **attrs))
    for i, data in enumerate(payloads):
        strobe = 15 if strobes is None else strobes[i]
        last = i == beats - 1 if flags is None else flags[i]
        await cycle(dut, model, f"W {i}", bready=1, **beat(data, strobe, last))
    await cycle(dut, model, "B", bready=1)


async def read_burst(dut, model, address, beats, stall=0, **attrs):
    await cycle(dut, model, "AR", **request("ar", address, beats, **attrs))
    for i in range(beats):
        for _ in range(stall):
            await cycle(dut, model, f"hold R {i}")
        await cycle(dut, model, f"consume R {i}", rready=1)


@cocotb.test()
async def test_write_data_before_address_and_b_stalls(dut):
    model = await setup(dut)
    incoming = beat(0x11223344, last=False)
    for _ in range(4):
        await cycle(dut, model, "W precedes AW", **incoming)
    await cycle(dut, model, "capture AW only", **request("aw", 36, 3, tx=3), **incoming)
    await cycle(dut, model, "transfer first W", **incoming, bready=1)
    for _ in range(3):
        await cycle(dut, model, "bubble in W", bready=1)
    await cycle(dut, model, "second W", **beat(0xAABBCCDD, last=False), awaddr=104)
    await cycle(dut, model, "last W creates B", **beat(0x8901EF23), bready=1)

    pending = request("aw", 56, 1, tx=1)
    for _ in range(6):
        await cycle(dut, model, "hold B and new AW", **pending)
    await cycle(dut, model, "B handshake excludes new AW", **pending, bready=1)
    await cycle(dut, model, "accept next AW", **pending)
    await cycle(dut, model, "next W", **beat(0xDEADBEEF))
    await cycle(dut, model, "next B", bready=1)
    await read_burst(dut, model, 36, 3)
    await read_burst(dut, model, 56, 1)


@cocotb.test()
async def test_byte_strobes_and_read_write_collisions(dut):
    model = await setup(dut)
    await write_burst(dut, model, 0, [0x11223344, 0x55667788])
    await cycle(dut, model, "prepare partial write", **request("aw", 0, 2, tx=2))
    await cycle(dut, model, "AR samples old word on same edge as W",
                **request("ar", 0, 2, tx=1), **beat(0xFFEEDDCC, strobe=0b0101, last=False))
    await cycle(dut, model, "held R ignores stores to another word", **beat(0x89ABCDEF, strobe=0b1001))
    await cycle(dut, model, "advance R to updated word", rready=1, bready=1)
    await cycle(dut, model, "consume updated word", rready=1)
    await write_burst(dut, model, 0, [0xFFFFFFFF, 0x01020304], strobes=[0, 0b0100])
    await read_burst(dut, model, 0, 2, stall=1)


@cocotb.test()
async def test_r_payload_stable_and_rlast_counts_handshakes(dut):
    model = await setup(dut)
    await write_burst(dut, model, 64, [0x16000, 0x27000, 0x38000, 0x49000, 0x50000])
    await cycle(dut, model, "start R burst", **request("ar", 64, 4, tx=3), arprot=7, arcache=9)
    next_ar = request("ar", 80, 1, tx=2)
    for i in range(4):
        for _ in range(i + 1):
            await cycle(dut, model, f"stall R beat {i}", **next_ar)
        await cycle(dut, model, f"drain R beat {i}", **next_ar, rready=1)
    await cycle(dut, model, "next AR after first R completes", **next_ar)
    await cycle(dut, model, "stall next single R")
    await cycle(dut, model, "complete next single R", rready=1)


@cocotb.test()
async def test_invalid_descriptors_and_wlast_recovery(dut):
    model = await setup(dut)
    await write_burst(dut, model, 0, [0x11223344, 0x55667788, 0x99AABBCC])
    await write_burst(dut, model, 252, [0x01010101])
    for address, attrs in [
        (0, {"size": 1}), (0, {"burst": 0}), (0, {"burst": 2}), (0, {"lock": 1}),
        (1, {}), (252, {}),
    ]:
        await write_burst(dut, model, address, [0xAAAA5555, 0xBBBB6666], **attrs)
        await read_burst(dut, model, address, 2, stall=1, **attrs)
    await write_burst(dut, model, 0, list(range(256)))
    await read_burst(dut, model, 0, 256)
    await read_burst(dut, model, 0, 3)
    await read_burst(dut, model, 252, 1)

    # Consume the captured length even after an early WLAST, or a missing final WLAST.
    await write_burst(dut, model, 0, [0xABCDEF01, 0xFEDCBA98, 0xF1E2D3C4], flags=[1, 0, 0])
    await read_burst(dut, model, 0, 3)
    await write_burst(dut, model, 4, [0x5A5A5A5A], flags=[0])
    await write_burst(dut, model, 4, [0x0BADCAFE], strobes=[0b0011])
    await read_burst(dut, model, 0, 3)


@cocotb.test()
async def test_full_window_and_reset_during_pending_responses(dut):
    model = await setup(dut)
    payloads = [0xABCD0000 + i for i in range(64)]
    await write_burst(dut, model, 0, payloads, tx=3)
    await read_burst(dut, model, 0, len(payloads))
    await cycle(dut, model, "pending read", **request("ar", 0, 3, tx=2))
    await cycle(dut, model, "pending write", **request("aw", 0, 2, tx=1))
    await cycle(dut, model, "write first new beat only", **beat(0xFFFF0000, last=False))
    await cycle(dut, model, "reset cancels stalled R and incomplete W", rst=1)
    await read_burst(dut, model, 0, len(payloads))
    await cycle(dut, model, "start single write", **request("aw", 8, 1, tx=1))
    await cycle(dut, model, "finish W", **beat(0xFEEDFEED))
    await cycle(dut, model, "reset cancels held B", rst=1, bready=1)
    await read_burst(dut, model, 8, 1)


@cocotb.test()
async def test_random_concurrent_bursts(dut):
    model = await setup(dut)
    rng = random.Random(48295)
    strobe_patterns = (0x0, 0x1, 0x3, 0x4, 0x5, 0x6, 0x9, 0xC, 0xF)
    pending_aw = pending_ar = None
    pending_w = False
    beats = []
    for i in range(1200):
        rst = int(rng.random() < 0.007)
        if pending_aw is None and not beats and rng.random() < 0.65:
            length = rng.randrange(1, 7)
            addr = 4 * rng.randrange(15)
            pending_aw = request("aw", addr, length, tx=rng.randrange(4))
            beats = [beat(rng.getrandbits(32), rng.choice(strobe_patterns), k == length - 1)
                     for k in range(length)]
        if pending_ar is None and rng.random() < 0.65:
            addr = 4 * rng.randrange(15)
            length = rng.randrange(1, 7)
            pending_ar = request("ar", addr, length, tx=rng.randrange(4))
        pending_w = pending_w or (bool(beats) and rng.random() < 0.80)
        before = model.outputs(rst)
        await cycle(dut, model, f"traffic {i}", rst=rst, bready=int(rng.random() < 0.6),
                    rready=int(rng.random() < 0.7), **(pending_aw or {}), **(pending_ar or {}),
                    **(beats[0] if pending_w else {}))
        if pending_w and before["wready"]:
            beats.pop(0)
            pending_w = False
        if rst:
            pending_aw = pending_ar = None
            pending_w = False
            beats.clear()
        if before["awready"]:
            pending_aw = None
        if before["arready"]:
            pending_ar = None
