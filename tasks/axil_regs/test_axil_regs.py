"""Cycle-accurate register and channel checks for axil_regs."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge, Timer

CTRL, STATUS, SCRATCH, IRQ = 0x0, 0x4, 0x8, 0xC
OKAY, SLVERR = 0, 2

INPUTS = dict.fromkeys((
    "rst", "status_in", "irq_set", "s_axi_awaddr", "s_axi_awprot", "s_axi_awvalid",
    "s_axi_wdata", "s_axi_wstrb", "s_axi_wvalid", "s_axi_bready", "s_axi_araddr",
    "s_axi_arprot", "s_axi_arvalid", "s_axi_rready",
), 0)


class Model:
    def __init__(self):
        self.registers = {CTRL: 0, SCRATCH: 0, IRQ: 0}
        self.address = None
        self.write_data = None
        self.bvalid = self.bresp = 0
        self.rvalid = self.rresp = self.rdata = 0

    def outputs(self, rst):
        return {
            "s_axi_awready": int(not rst and not self.bvalid and self.address is None),
            "s_axi_wready": int(not rst and not self.bvalid and self.write_data is None),
            "s_axi_bvalid": self.bvalid,
            "s_axi_bresp": self.bresp,
            "s_axi_arready": int(not rst and not self.rvalid),
            "s_axi_rvalid": self.rvalid,
            "s_axi_rresp": self.rresp,
            "s_axi_rdata": self.rdata,
        }

    def tick(self, inputs):
        if inputs["rst"]:
            self.__init__()
            return

        before = self.outputs(rst=0)
        if self.rvalid and inputs["s_axi_rready"]:
            self.rvalid = 0
        if inputs["s_axi_arvalid"] and before["s_axi_arready"]:
            address = inputs["s_axi_araddr"]
            self.rvalid = 1
            read_map = {**self.registers, STATUS: inputs["status_in"]}
            self.rresp = OKAY if address in read_map else SLVERR
            self.rdata = read_map.get(address, 0)

        if self.bvalid and inputs["s_axi_bready"]:
            self.bvalid = 0
        if self.address is not None and self.write_data is not None:
            addr = self.address
            data, strobes = self.write_data
            mask = sum(0xFF << (8 * i) for i in range(4) if (strobes >> i) & 1)
            self.bvalid = 1
            self.bresp = OKAY if addr in self.registers else SLVERR
            if addr in (CTRL, SCRATCH):
                self.registers[addr] = (self.registers[addr] & ~mask) | (data & mask)
            if addr == IRQ:
                self.registers[IRQ] &= ~(data & mask)
            self.address = None
            self.write_data = None
        self.registers[IRQ] |= inputs["irq_set"]

        if inputs["s_axi_awvalid"] and before["s_axi_awready"]:
            self.address = inputs["s_axi_awaddr"]
        if inputs["s_axi_wvalid"] and before["s_axi_wready"]:
            self.write_data = inputs["s_axi_wdata"], inputs["s_axi_wstrb"]


async def setup(dut):
    for name, value in INPUTS.items():
        getattr(dut, name).value = value
    dut.rst.value = 1
    Clock(dut.clk, 10, unit="ns").start()
    await ClockCycles(dut.clk, 2)
    await FallingEdge(dut.clk)
    return Model()


def check_outputs(dut, expected, inputs, label):
    for signal, exp in expected.items():
        value = getattr(dut, signal).value
        try:
            got = int(value)
        except ValueError:
            got = str(value)
        if got != exp:
            stimulus = " ".join(f"{name.removeprefix('s_axi_')}={value:#x}"
                                for name, value in inputs.items())
            assert got == exp, (
                f"{label} {stimulus}: {signal.removeprefix('s_axi_')}={got}, expected {exp}"
            )


async def cycle(dut, model, label="", **signals):
    inputs = {**INPUTS, **signals}
    for name, value in inputs.items():
        getattr(dut, name).value = value
    await Timer(1, unit="ns")
    await ReadOnly()
    check_outputs(dut, model.outputs(inputs["rst"]), inputs, f"{label} before edge")
    await RisingEdge(dut.clk)
    model.tick(inputs)
    await ReadOnly()
    check_outputs(dut, model.outputs(inputs["rst"]), inputs, f"{label} after edge")
    await FallingEdge(dut.clk)


def aw(address, prot=0):
    return {"s_axi_awaddr": address, "s_axi_awprot": prot, "s_axi_awvalid": 1}


def w(data, strobe=15):
    return {"s_axi_wdata": data, "s_axi_wstrb": strobe, "s_axi_wvalid": 1}


def ar(address, prot=0):
    return {"s_axi_araddr": address, "s_axi_arprot": prot, "s_axi_arvalid": 1}


async def write(dut, model, address, data, strobes=15, pulse=0):
    await cycle(dut, model, "accept write", **aw(address), **w(data, strobes))
    await cycle(dut, model, "commit write", irq_set=pulse, s_axi_bready=1)
    await cycle(dut, model, "consume B", s_axi_bready=1)


async def read(dut, model, address, status=0):
    await cycle(dut, model, "accept read", status_in=status, **ar(address))
    await cycle(dut, model, "consume R", s_axi_rready=1)


@cocotb.test()
async def test_write_channel_orders_and_reset(dut):
    model = await setup(dut)
    await cycle(dut, model, "address first", **aw(CTRL, prot=7))
    for _ in range(4):
        await cycle(dut, model, "hold address slot", s_axi_awaddr=IRQ, s_axi_bready=1)
    await cycle(dut, model, "pair address with data", **w(0xABCDEF01), s_axi_bready=1)
    await cycle(dut, model, "commit first write", s_axi_bready=1)
    await cycle(dut, model, "consume first B", s_axi_bready=1)
    await read(dut, model, CTRL)

    await cycle(dut, model, "data first", **w(0xFEDCBA98))
    for _ in range(3):
        await cycle(dut, model, "hold data slot", s_axi_wdata=0xFFFFFFFF, s_axi_wstrb=0)
    await cycle(dut, model, "pair data with address", **aw(SCRATCH))
    await cycle(dut, model, "commit second write")
    await cycle(dut, model, "consume second B", s_axi_bready=1)
    await read(dut, model, SCRATCH)

    await cycle(dut, model, "start partial transfer", **aw(IRQ))
    await cycle(dut, model, "discard pending address", rst=1, irq_set=0xFFFFFFFF)
    await cycle(dut, model, "fresh data needs fresh address", **w(0x0F1E2D3C))
    await cycle(dut, model, "fresh transaction", **aw(CTRL))
    await cycle(dut, model, "commit after reset")
    await cycle(dut, model, "consume B after reset", s_axi_bready=1)
    await read(dut, model, CTRL)
    await read(dut, model, SCRATCH)
    await read(dut, model, IRQ)


@cocotb.test()
async def test_byte_enables_and_decode(dut):
    model = await setup(dut)
    for address in (CTRL, SCRATCH):
        await write(dut, model, address, 0x11223344)
        await write(dut, model, address, 0xFEDCBA98, strobes=0b0101)
        await read(dut, model, address)
        await write(dut, model, address, 0xFFFFFFFF, strobes=0)
        await read(dut, model, address)
    await write(dut, model, STATUS, 0xDEADBEEF)
    await read(dut, model, STATUS, status=0xABCD0123)
    for address in (0x1, 0x2, 0x3, 0x6, 0x7, 0x9, 0xB, 0xD, 0xF):
        await write(dut, model, address, 0xFFFFFFFF)
        await read(dut, model, address)
    await read(dut, model, CTRL)
    await read(dut, model, SCRATCH)


@cocotb.test()
async def test_concurrent_access_and_response_backpressure(dut):
    model = await setup(dut)
    await write(dut, model, SCRATCH, 0x12345678)
    await cycle(dut, model, "partial overwrite", **aw(SCRATCH), **w(0xDEADBEEF, 0b1001))
    await cycle(dut, model, "read old scratch on commit", **ar(SCRATCH))
    second = {**aw(CTRL), **w(0xA5A55A5A), **ar(STATUS, prot=5), "status_in": 0x8100}
    for _ in range(8):
        await cycle(dut, model, "hold both responses and block all requests", **second)
    await cycle(dut, model, "release only B", **second, s_axi_bready=1)
    await cycle(dut, model, "accept next write only", **second)
    read_request = ar(STATUS, prot=5)
    await cycle(dut, model, "commit write while old R releases", **read_request, s_axi_rready=1)
    await cycle(dut, model, "accept new status read", **read_request, status_in=0xAA550000)
    for value in (0, 0xFFFFFFFF, 0xDEAD0000):
        await cycle(dut, model, "hold captured status", status_in=value)
    await cycle(dut, model, "release both", s_axi_bready=1, s_axi_rready=1)
    await read(dut, model, SCRATCH)
    await read(dut, model, CTRL)
    await cycle(dut, model, "prepare reset of busy read and write", **aw(STATUS), **w(0), **ar(CTRL))
    await cycle(dut, model, "both responses pending")
    await cycle(dut, model, "reset cancels both responses", rst=1)
    await read(dut, model, CTRL)


@cocotb.test()
async def test_irq_byte_enables_and_set_priority(dut):
    model = await setup(dut)
    await cycle(dut, model, "set all IRQ bits", irq_set=0xFFFFFFFF)
    await write(dut, model, IRQ, 0xFFFF00FF, strobes=0b0101, pulse=0x00050001)
    await read(dut, model, IRQ)
    await write(dut, model, IRQ, 0xFFFFFFFF, strobes=0b1000)
    await read(dut, model, IRQ)
    await write(dut, model, IRQ, 0xFFFFFFFF, strobes=0)
    await read(dut, model, IRQ)


@cocotb.test()
async def test_irq_pre_edge_snapshot(dut):
    model = await setup(dut)
    await cycle(dut, model, "set first IRQ", irq_set=0x00100020)
    await cycle(dut, model, "queue clear", **aw(IRQ), **w(0x00100020))
    await cycle(dut, model, "capture previous IRQ", **ar(IRQ), irq_set=0x00110000)
    await cycle(dut, model, "hold snapshot while ORing a new pulse", irq_set=0x80000000)
    await cycle(dut, model, "drain responses", s_axi_rready=1, s_axi_bready=1)
    await read(dut, model, IRQ)


@cocotb.test()
async def test_random_channel_skew_and_backpressure(dut):
    model = await setup(dut)
    rng = random.Random(532)
    # Sample aligned registers and representative invalid reads at fixed addresses.
    read_addrs = (CTRL, STATUS, SCRATCH, IRQ, 0x1, 0x6, 0xB, 0xF)
    write_addrs = (CTRL, STATUS, SCRATCH, IRQ, 0x5, 0x9, 0xE)
    pending_aw = pending_w = pending_ar = None
    for i in range(900):
        rst = int(rng.random() < 0.01)
        if pending_aw is None and rng.random() < 0.6:
            pending_aw = aw(rng.choice(write_addrs), rng.randrange(8))
        if pending_w is None and rng.random() < 0.6:
            pending_w = w(rng.getrandbits(32), rng.randrange(16))
        if pending_ar is None and rng.random() < 0.7:
            pending_ar = ar(rng.choice(read_addrs), rng.randrange(8))
        before = model.outputs(rst)
        await cycle(
            dut, model, f"traffic cycle {i}", rst=rst, status_in=rng.getrandbits(32),
            irq_set=rng.getrandbits(32) if rng.random() < 0.16 else 0,
            s_axi_bready=int(rng.random() < 0.5), s_axi_rready=int(rng.random() < 0.5),
            **(pending_aw or {}), **(pending_w or {}), **(pending_ar or {}),
        )
        if rst or before["s_axi_awready"]:
            pending_aw = None
        if rst or before["s_axi_wready"]:
            pending_w = None
        if rst or before["s_axi_arready"]:
            pending_ar = None
