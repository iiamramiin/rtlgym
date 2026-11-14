"""Compare prefix CRCs against the standard library's Ethernet CRC-32."""

import random
from zlib import crc32

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge


class Model:
    def __init__(self):
        self.crc = 0
        self.valid = 0

    def tick(self, rst, start, valid, data):
        self.valid = int(valid and not rst)
        if rst or start:
            self.crc = 0
        if self.valid:
            self.crc = crc32(bytes([data]), self.crc)


async def setup(dut):
    dut.rst.value = 1
    dut.start.value = 0
    dut.in_valid.value = 0
    dut.data.value = 0
    Clock(dut.clk, 10, unit="ns").start()
    await ClockCycles(dut.clk, 2)
    await FallingEdge(dut.clk)
    return Model()


async def cycle(dut, model, *, rst=0, start=0, valid=0, data=0, tag="", known_crc=None):
    dut.rst.value = rst
    dut.start.value = start
    dut.in_valid.value = valid
    dut.data.value = data
    await RisingEdge(dut.clk)
    model.tick(rst, start, valid, data)
    await ReadOnly()
    got_valid = str(dut.out_valid.value)
    got_crc = str(dut.crc.value)
    expected_crc = model.crc if known_crc is None else known_crc
    inputs = f"{tag} rst={rst} start={start} in_valid={valid} data=0x{data:02x}"
    assert got_valid == str(model.valid), f"{inputs}: out_valid={got_valid}, expected {model.valid}"
    assert got_crc == f"{expected_crc:032b}", (
        f"{inputs}: crc={got_crc} (binary), expected 0x{expected_crc:08x}"
    )
    await FallingEdge(dut.clk)


@cocotb.test()
async def test_standard_check_string(dut):
    model = await setup(dut)
    for i, byte in enumerate(b"123456789"):
        await cycle(dut, model, start=int(i == 0), valid=1, data=byte, tag=f"ASCII prefix byte {i}")
    await cycle(dut, model, data=0xFF, known_crc=0xCBF43926, tag="idle after ASCII 123456789")


@cocotb.test()
async def test_gaps_and_zero_bytes(dut):
    model = await setup(dut)
    await cycle(dut, model, start=1, data=0xFF, tag="empty stream")
    for i, byte in enumerate((0x00, 0x01, 0x80, 0xFF, 0x00)):
        await cycle(dut, model, start=int(i == 0), valid=1, data=byte, tag=f"accepted byte {i}")
        await cycle(dut, model, data=byte ^ 0xFF, tag=f"gap after byte {i}")
        await cycle(dut, model, data=byte, tag=f"second gap after byte {i}")


@cocotb.test()
async def test_restart_and_accept_same_cycle(dut):
    model = await setup(dut)
    for byte in (0x37, 0x80, 0xEF):
        await cycle(dut, model, valid=1, data=byte, tag="old stream")
    for byte in (0xA2, 0x11, 0xFE):
        await cycle(dut, model, start=1, valid=1, data=byte, tag="consecutive restarts")
    await cycle(dut, model, valid=1, data=0, tag="continue after restart")
    await cycle(dut, model, start=1, data=0x4A, tag="restart without a byte")


@cocotb.test()
async def test_reset_dominates_start_and_valid(dut):
    model = await setup(dut)
    await cycle(dut, model, valid=1, data=0x7B, tag="before reset")
    await cycle(dut, model, rst=1, start=1, valid=1, data=0xC3, tag="reset with start and valid")
    await cycle(dut, model, rst=1, valid=1, data=0xAB, tag="reset held high")
    await cycle(dut, model, data=0xFF, tag="first cycle after reset")
    await cycle(dut, model, valid=1, data=0xE7, tag="first byte after reset")


@cocotb.test()
async def test_seeded_streams(dut):
    model = await setup(dut)
    rng = random.Random(37)
    for i in range(640):
        rst = int(rng.random() < 0.015)
        start = int(rng.random() < 0.12)
        valid = int(rng.random() < 0.68)
        byte = rng.randrange(256)
        await cycle(dut, model, rst=rst, start=start, valid=valid, data=byte, tag=f"random cycle {i}")
