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


_FENCE_RE = re.compile(r"```(?:systemverilog|verilog|sv|v)?[ \t]*\n(.*?)```", re.S | re.I)


def extract_code(text: str) -> str:
    """Pull RTL out of an LLM reply. Uses the last fenced block that has a module."""
    blocks = [b for b in _FENCE_RE.findall(text) if "module" in b]
    if blocks:
        return blocks[-1].strip() + "\n"
    return text.strip() + "\n"
