# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Static checks on candidate RTL that run before any tool.

These close the cheapest reward-hacking routes: ending the simulation early,
touching the file system, or pulling in files the agent should not see.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FORBIDDEN = {
    r"\$finish\b": "$finish ends the simulation early",
    r"\$stop\b": "$stop ends the simulation early",
    r"\$fatal\b": "$fatal ends the simulation early",
    r"\$(fopen|fwrite|fdisplay|fscanf|fgets|fread|readmem[bh]|writemem[bh]|system)\b":
        "file or OS access is not allowed",
    r"`include\b": "`include is not allowed; submit one self-contained file",
    r"\$(random|urandom)\b": "randomness in the design is not allowed",
    r"\$(dumpfile|dumpvars)\b": "waveform dumping is not allowed",
}

MAX_SOURCE_BYTES = 64 * 1024


@dataclass
class CheckResult:
    ok: bool
    violations: list[str]


def _strip_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", " ", code, flags=re.S)
    return re.sub(r"//[^\n]*", " ", code)


def static_check(code: str, top: str) -> CheckResult:
    violations: list[str] = []
    if len(code.encode()) > MAX_SOURCE_BYTES:
        violations.append(f"source exceeds {MAX_SOURCE_BYTES} bytes")
    body = _strip_comments(code)
    for pattern, why in FORBIDDEN.items():
        m = re.search(pattern, body)
        if m:
            violations.append(f"'{m.group(0)}': {why}")
    if not re.search(rf"\bmodule\s+{re.escape(top)}\b", body):
        violations.append(f"no module named '{top}' found")
    return CheckResult(not violations, violations)


# A fenced block: ``` or ~~~, any language tag, up to the matching closing fence.
_FENCE_RE = re.compile(r"(```|~~~)[^\n]*\n(.*?)\1", re.S)
_OPEN_FENCE_RE = re.compile(r"(```|~~~)[^\n]*\n")
# A module declaration starts a line ("module name (", "#(" or ";"), so the word
# "module" in prose ("The module below...") is not taken for code.
_MODULE_RE = re.compile(r"^[ \t]*(?:macro)?module\s+([A-Za-z_]\w*)\s*(?:#|\(|;).*?\bendmodule\b",
                        re.S | re.M)


def _code_regions(text: str) -> list[str]:
    """Fenced blocks in order, plus the tail of an unclosed fence (a reply cut off
    mid-code). Without fences, the whole text is one region."""
    regions = [m.group(2) for m in _FENCE_RE.finditer(text)]
    rest = _FENCE_RE.sub("", text)
    m = _OPEN_FENCE_RE.search(rest)
    if m:
        regions.append(rest[m.end():])
    return regions or [text]


def extract_code(text: str, top: str | None = None) -> str:
    """Pull RTL out of an LLM reply; the same rules for every agent.

    The design is the last code region that defines ``top`` (or, without ``top``,
    the last region with a module). Helper modules that the design instantiates
    but defines elsewhere in the reply (another fence, or bare text) are added,
    using the last version of each name; modules the design does not use, such as
    a testbench, are left out. Prose around bare modules is dropped. If no module
    is found, the reply is returned as is, and grading reports the problem.
    """
    regions = _code_regions(text)
    defs: dict[str, str] = {}               # module name -> its last definition
    region_mods: list[list[str]] = []
    for r in regions:
        names = []
        for m in _MODULE_RE.finditer(r):
            defs[m.group(1)] = m.group(0).strip()
            names.append(m.group(1))
        region_mods.append(names)
    if not defs:
        return text.strip() + "\n"

    def pick(want) -> int | None:
        hits = [i for i, names in enumerate(region_mods) if want(names)]
        return hits[-1] if hits else None

    base_i = pick(lambda n: top in n) if top else None
    if base_i is None:
        base_i = pick(bool)
    base_names = region_mods[base_i]
    root = top if top in base_names else base_names[-1]

    # Modules reachable from the root by instantiation (name used in a body).
    needed, todo = [], [root]
    while todo:
        name = todo.pop()
        if name in needed:
            continue
        needed.append(name)
        body = defs[name].split("\n", 1)[1] if "\n" in defs[name] else ""
        todo += [d for d in defs if d not in needed and re.search(rf"\b{d}\b", body)]

    fenced = len(regions) > 1 or regions[0] is not text
    if fenced:
        # Keep the base region whole (it may hold `timescale, packages, ...),
        # swapping in the last version of any module it defines.
        code = regions[base_i]
        for m in reversed(list(_MODULE_RE.finditer(code))):
            if m.group(1) in needed and defs[m.group(1)] != m.group(0).strip():
                code = code[:m.start()] + defs[m.group(1)] + code[m.end():]
        extra = [defs[n] for n in needed if n not in base_names]
    else:
        # Bare text: keep only the modules, in the order they appear.
        order = [m.group(1) for m in _MODULE_RE.finditer(text)]
        code = "\n\n".join(defs[n] for n in dict.fromkeys(order) if n in needed)
        extra = []
    return "\n\n".join([code.strip(), *extra]).strip() + "\n"
