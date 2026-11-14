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


def _fenced(text: str) -> tuple[list[tuple[int, int]], str]:
    """Spans of the content of each fenced block, in order (plus the tail of an
    unclosed fence: a reply cut off mid-code), and the bare text: the reply with
    every fenced block blanked out, so positions still line up."""
    closed = list(_FENCE_RE.finditer(text))
    spans = [m.span(2) for m in closed]
    blank = [m.span() for m in closed]
    m = _OPEN_FENCE_RE.search(text, closed[-1].end() if closed else 0)
    if m:
        spans.append((m.end(), len(text)))
        blank.append((m.start(), len(text)))
    bare = list(text)
    for a, b in blank:
        bare[a:b] = " " * (b - a)
    return spans, "".join(bare)


def _module_body(src: str) -> str:
    """The module's body, for finding what it instantiates: everything after its
    header (which ends at the first ';'; ANSI port and parameter lists contain none,
    so one-line modules work too), with comments and string literals removed."""
    i = src.find(";")
    body = src[i + 1:] if i >= 0 else ""
    return re.sub(r'"(?:\\.|[^"\\\n])*"', " ", _strip_comments(body))


def _instantiates(body: str, name: str) -> bool:
    """True if ``body`` instantiates module ``name``: the name followed by a
    parameter list (``name #(...)``) or by an instance name, an optional instance
    array range, and a port list (``name u0 (...)``, ``name u[3:0] (...)``).
    A mere mention ("unlike tb, ...", ``tb_done = 1``) does not count."""
    return re.search(rf"\b{re.escape(name)}\s*(?:#\s*\(|[A-Za-z_]\w*\s*(?:\[[^\]]*\]\s*)?\()",
                     body) is not None


def extract_code(text: str, top: str | None = None) -> str:
    """Pull RTL out of an LLM reply; the same rules for every agent.

    Modules are collected from every code fence and from the bare text around them.
    The design is the last fenced block that defines ``top`` (or, without ``top``,
    the last fenced block with a module); if no fence holds the design, the modules
    in the bare text are used. Helper modules that the design instantiates but that
    are defined elsewhere in the reply are added, using the last version of each
    name; modules the design does not use, such as a testbench, are left out, and so
    is prose. If no module is found, the reply is returned as is, and grading
    reports the problem.
    """
    spans, bare = _fenced(text)
    unclosed = bool(spans) and spans[-1][1] == len(text) and not text.rstrip().endswith(
        ("```", "~~~"))
    found = []                     # (position, name, source, region); region -1 = bare
    for i, (a, b) in enumerate(spans):
        for m in _MODULE_RE.finditer(text, a, b):
            found.append((m.start(), m.group(1), m.group(0).strip(), i))
    for m in _MODULE_RE.finditer(bare):
        found.append((m.start(), m.group(1), m.group(0).strip(), -1))
    if not found:
        # No complete module. If the reply was cut off inside a code fence, hand the
        # compiler just that code, so its error points at the real problem (the
        # missing end) rather than at the prose before it.
        if unclosed and re.search(r"\bmodule\b", text[spans[-1][0]:]):
            return text[spans[-1][0]:].strip() + "\n"
        return text.strip() + "\n"
    found.sort()
    defs = {name: src for _, name, src, _ in found}          # last version of each name

    fenced_top = [r for _, n, _, r in found if r >= 0 and n == top] if top else []
    bare_top = top is not None and any(n == top for _, n, _, r in found if r < 0)
    fenced_any = [r for _, _, _, r in found if r >= 0]
    if fenced_top:
        base = fenced_top[-1]
    elif bare_top or not fenced_any:
        base = -1
    else:
        base = fenced_any[-1]
    base_names = [n for _, n, _, r in found if r == base]
    root = top if top in base_names else base_names[-1]

    # Modules reachable from the root by instantiation (name used in a body).
    needed, todo = [], [root]
    while todo:
        name = todo.pop()
        if name in needed:
            continue
        needed.append(name)
        body = _module_body(defs[name])
        todo += [d for d in defs if d not in needed and _instantiates(body, d)]

    if base >= 0:
        # Keep the fenced block whole (it may hold `timescale, packages, ...),
        # swapping in the last version of any module it defines.
        a, b = spans[base]
        code = text[a:b]
        for m in reversed(list(_MODULE_RE.finditer(code))):
            if m.group(1) in needed and defs[m.group(1)] != m.group(0).strip():
                code = code[:m.start()] + defs[m.group(1)] + code[m.end():]
    else:
        # Bare text: keep only the needed modules, in the order they appear.
        order = [n for _, n, _, r in found if r < 0]
        code = "\n\n".join(defs[n] for n in dict.fromkeys(order) if n in needed)
    extra = [defs[n] for n in needed if n not in base_names]
    return "\n\n".join([code.strip(), *extra]).strip() + "\n"
