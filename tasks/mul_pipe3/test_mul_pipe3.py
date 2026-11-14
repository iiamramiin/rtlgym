"""Cycle scoreboard for the full-width signed multiplier."""

import random
from collections import deque

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

WIDTH = 16
LIMIT = 1 << (WIDTH - 1)
OPERAND_MASK = (1 << WIDTH) - 1


class Model:
    def __init__(self):
        self.pending = deque([None] * 3)

    def tick(self, rst, valid, a, b):
        if rst:
            self.pending = deque([None] * 3)
            return 0, 0
        self.pending.append(a * b if valid else None)
        due = self.pending.popleft()
        return (0, 0) if due is None else (1, due)


async def setup(dut):
    dut.rst.value = 1
    dut.in_valid.value = 0
    dut.a.value = 0
    dut.b.value = 0
    Clock(dut.clk, 10, unit="ns").start()
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    return Model()


async def cycle(dut, model, valid=0, a=0, b=0, rst=0, tag=""):
    dut.rst.value = rst
    dut.in_valid.value = valid
    dut.a.value = a & OPERAND_MASK
    dut.b.value = b & OPERAND_MASK
    await RisingEdge(dut.clk)
    expected_valid, expected_product = model.tick(rst, valid, a, b)
    await ReadOnly()
    valid_bits, product_bits = dut.out_valid.value, dut.product.value
    got = (str(valid_bits), str(product_bits))
    expected = (str(expected_valid), f"{expected_product & ((1 << (2 * WIDTH)) - 1):0{2 * WIDTH}b}")
    assert got == expected, (
        f"{tag} rst={rst} in_valid={valid} a={a} b={b}: "
        f"(out_valid,product bits)={got}, expected {expected} (product={expected_product})"
    )
    await FallingEdge(dut.clk)


async def drain(dut, model):
    for i in range(3):
        await cycle(dut, model, tag=f"drain {i}")


@cocotb.test()
async def test_exact_latency(dut):
    model = await setup(dut)
    await cycle(dut, model, valid=1, a=17, b=19, tag="single pair")
    await drain(dut, model)


@cocotb.test()
async def test_signed_limits(dut):
    model = await setup(dut)
    pairs = [(-LIMIT, -1), (-1, -LIMIT), (-LIMIT, LIMIT - 1), (LIMIT - 1, -LIMIT),
             (LIMIT - 1, LIMIT - 1), (-1, -1), (-LIMIT, 0), (0, -LIMIT), (0, 0)]
    for a, b in pairs:
        await cycle(dut, model, valid=1, a=a, b=b, tag="signed limit")
    await drain(dut, model)


@cocotb.test()
async def test_bubbles_and_throughput(dut):
    model = await setup(dut)
    for i, v in enumerate((1, 1, 0, 1, 0, 0, 1, 1, 1, 1, 0, 1)):
        await cycle(dut, model, valid=v, a=i + 11, b=-19 + i, tag=f"burst {i}")
    await drain(dut, model)


@cocotb.test()
async def test_reset_flushes_in_flight(dut):
    model = await setup(dut)
    for i in range(4):
        await cycle(dut, model, valid=1, a=i + 1, b=27, tag=f"before reset {i}")
    await cycle(dut, model, valid=1, a=11, b=29, rst=1, tag="reset discards input and queue")
    await cycle(dut, model, valid=1, a=-21, b=13, tag="immediate restart")
    await drain(dut, model)


@cocotb.test()
async def test_random_traffic(dut):
    model = await setup(dut)
    rng = random.Random(41)
    for i in range(640):
        a, b = rng.randrange(-LIMIT, LIMIT), rng.randrange(-LIMIT, LIMIT)
        if a == b == -LIMIT:
            b += 1
        await cycle(dut, model, valid=int(rng.random() < 0.72), a=a, b=b,
                    rst=int(rng.random() < 0.02), tag=f"random {i}")
    await drain(dut, model)
