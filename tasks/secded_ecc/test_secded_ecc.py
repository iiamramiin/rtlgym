# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Check a shortened extended Hamming code with an independent parity oracle."""

import random
from itertools import combinations

import cocotb
from cocotb.triggers import Timer


class Model:
    def __init__(self, data_width):
        parity_width = 1
        while (1 << parity_width) < data_width + parity_width + 1:
            parity_width += 1
        self.parity_width = parity_width
        self.body_width = data_width + parity_width
        self.code_width = self.body_width + 1
        self.data_positions = [p for p in range(1, self.body_width + 1) if p & (p - 1)]
        self.parity_groups = [
            sum(1 << (p - 1) for p in range(1, self.body_width + 1) if p & (1 << k))
            for k in range(parity_width)
        ]

    def encode(self, payload):
        body = sum(((payload >> i) & 1) << (p - 1) for i, p in enumerate(self.data_positions))
        check_bits = [(body & mask).bit_count() % 2 for mask in self.parity_groups]
        body |= sum(bit << ((1 << k) - 1) for k, bit in enumerate(check_bits))
        return body | (body.bit_count() % 2) << self.body_width

    def decode(self, code):
        odd = code.bit_count() % 2
        syndrome = sum(((code & mask).bit_count() % 2) << k for k, mask in enumerate(self.parity_groups))
        corrected = odd and syndrome <= self.body_width
        uncorrectable = (odd and syndrome > self.body_width) or (not odd and syndrome != 0)
        if corrected and syndrome:
            code ^= 1 << (syndrome - 1)
        data = sum(((code >> (p - 1)) & 1) << i for i, p in enumerate(self.data_positions))
        return data, int(corrected), int(uncorrectable)


async def check(dut, model, payload, code, tag):
    dut.enc_data.value = payload
    dut.dec_code.value = code
    await Timer(1, unit="ns")
    want_code = model.encode(payload)
    want_data, want_corrected, want_uncorrectable = model.decode(code)
    got_code = str(dut.enc_code.value)
    got_decode = (str(dut.dec_data.value), str(dut.corrected.value), str(dut.uncorrectable.value))
    want_decode = (f"{want_data:0{len(dut.dec_data)}b}", str(want_corrected), str(want_uncorrectable))
    inputs = f"{tag} enc_data=0x{payload:x} dec_code=0x{code:x}"
    assert got_code == f"{want_code:0{model.code_width}b}", (
        f"{inputs}: enc_code={got_code} (binary), expected 0x{want_code:x}"
    )
    assert got_decode == want_decode, (
        f"{inputs}: (dec_data, corrected, uncorrectable)={got_decode} (binary), expected {want_decode}"
    )


@cocotb.test()
async def test_clean_and_one_hot_payloads(dut):
    width = len(dut.enc_data)
    model = Model(width)
    for payload in (0, (1 << width) - 1, *(1 << i for i in range(width))):
        enc_payload = payload ^ ((1 << width) - 1)
        await check(dut, model, enc_payload, model.encode(payload), "clean decode, separate encoder input")


@cocotb.test()
async def test_each_single_bit_is_correctable(dut):
    width = len(dut.enc_data)
    model = Model(width)
    for payload in (0, (1 << width) - 1, 0x5A6C & ((1 << width) - 1)):
        code = model.encode(payload)
        for bit in range(model.code_width):
            await check(dut, model, payload, code ^ (1 << bit), f"single flipped code bit {bit}")


@cocotb.test()
async def test_each_double_error_is_uncorrectable(dut):
    width = len(dut.enc_data)
    model = Model(width)
    payload = 0xC7F1 & ((1 << width) - 1)
    code = model.encode(payload)
    for a, b in combinations(range(model.code_width), 2):
        await check(dut, model, payload, code ^ (1 << a) ^ (1 << b), f"double code bits {a},{b}")


@cocotb.test()
async def test_miscorrection_and_invalid_shortened_positions(dut):
    width = len(dut.enc_data)
    model = Model(width)
    for syndrome in (3, model.body_width, model.body_width + 2):
        if syndrome >= (1 << model.parity_width):
            continue
        code = sum(1 << ((1 << k) - 1) for k in range(model.parity_width) if (syndrome >> k) & 1)
        if code.bit_count() % 2 == 0:
            code |= 1 << model.body_width
        await check(dut, model, 0, code, f"odd codeword with syndrome {syndrome}")


@cocotb.test()
async def test_seeded_mixed_errors(dut):
    width = len(dut.enc_data)
    model = Model(width)
    rng = random.Random(50617)
    for i in range(640):
        code = model.encode(rng.getrandbits(width))
        error_count = rng.randrange(3)
        for bit in rng.sample(range(model.code_width), error_count):
            code ^= 1 << bit
        await check(dut, model, rng.getrandbits(width), code, f"sample {i} with {error_count} flipped bits")
