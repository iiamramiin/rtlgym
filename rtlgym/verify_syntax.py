# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ramin Rajaei

"""Validate native observer XML and regenerate the permitted checker language.

Only regenerated HDL leaves this module. The submitted text is never passed to
the simulator or formal engine, and the design conversion fallback is unused.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .tools import run, tail

MAX_SOURCE_BYTES = 64 * 1024
MAX_XML_BYTES = 4 * 1024 * 1024
MAX_NODES = 12000
MAX_PRIVATE_BITS = 4096
MAX_LOOP_STEPS = 128
MAX_ASSERTIONS = 64
_PREFIX = "__rtlgym_"
_TOKEN = re.compile(
    r'\s+|//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\\[^\s]+|'
    r"[a-zA-Z_$][a-zA-Z0-9_$]*|[0-9][a-zA-Z0-9_'?]*|.", re.S,
)
_NUMBER = re.compile(r"(\d+)'(s?)([hbd])([0-9a-f]+)", re.I)


@dataclass
class CheckerValidation:
    valid: bool
    reason: str = ""
    source: str = ""
    instrumented: str = ""
    assert_count: int = 0
    state_bits: int = 0
    inconclusive: bool = False


class InvalidChecker(ValueError):
    pass


@dataclass
class _Symbol:
    name: str
    dtype: str
    input_port: bool = False
    constant: bool = False
    function_local: bool = False
    temporary: bool = False


def _number(text: str) -> int:
    match = _NUMBER.fullmatch(text)
    if match is None:
        raise InvalidChecker("Only defined integer constants are supported")
    width, signed, base, digits = match.groups()
    bits = int(width)
    if not 0 < bits <= 256:
        raise InvalidChecker("Constant width exceeds the checker limit")
    value = int(digits, {"h": 16, "b": 2, "d": 10}[base.lower()])
    if signed and value & (1 << (bits - 1)):
        value -= 1 << bits
    return value


def _tokens(code: str) -> list[tuple[str, int]]:
    tokens = []
    for match in _TOKEN.finditer(code):
        text = match.group()
        if text.isspace() or text.startswith(("//", "/*")):
            continue
        if text == "`":
            raise InvalidChecker("Preprocessor directives and includes are unsupported")
        if text in ("import", "export", "bind", "force", "release", "assume", "restrict", "cover",
                    "casex", "casez", "unique", "unique0", "priority"):
            raise InvalidChecker(f"Unsupported checker construct {text}")
        if text.startswith("$") and text not in ("$signed", "$unsigned", "$clog2", "$bits"):
            raise InvalidChecker("Only pure integer cast and width system functions are supported")
        tokens.append((text, match.start()))
    if sum(text == "module" for text, _ in tokens) != 1 or sum(
            text == "endmodule" for text, _ in tokens) != 1:
        raise InvalidChecker("Submit exactly one rtl_checker module")
    return tokens


def _without_comments(code: str) -> str:
    # Preserve source coordinates while preventing submitted tool pragmas from
    # disabling the diagnostics used to validate monitor state.
    def replace(match: re.Match[str]) -> str:
        text = match.group()
        if text.startswith(("//", "/*")):
            return "".join("\n" if char == "\n" else " " for char in text)
        return text

    return _TOKEN.sub(replace, code)


_BINARY = {
    "add": "+", "sub": "-", "mul": "*", "and": "&", "or": "|", "xor": "^",
    "eq": "==", "neq": "!=", "eqcase": "===", "neqcase": "!==",
    "lt": "<", "lte": "<=", "gt": ">", "gte": ">=",
    "lts": "<", "ltes": "<=", "gts": ">", "gtes": ">=",
    "logand": "&&", "logor": "||", "shiftl": "<<", "shiftr": ">>", "shiftrs": ">>>",
}
_UNARY = {
    "not": "~", "lognot": "!", "negate": "-", "redand": "&", "redor": "|",
    "redxor": "^", "redxnor": "~^",
}


class _Renderer:
    def __init__(self, document: ET.Element, code: str, ports: dict, clock: str | None,
                 reset: str | None):
        self.document, self.code, self.clock, self.reset = document, code, clock, reset
        self.tokens = _tokens(code)
        modules = document.findall("./netlist/module")
        if len(modules) != 1 or modules[0].get("origName") != "rtl_checker":
            raise InvalidChecker("Submit exactly one rtl_checker module")
        self.module = modules[0]
        self.types = {node.get("id"): node for node in document.findall("./netlist/typetable/*")}
        self.ports = ports
        self.scopes: list[dict[str, _Symbol]] = [{}]
        self.constants: dict[str, int] = {}
        self.functions = {node.get("name"): node for node in self.module.findall("func")}
        if len(self.functions) > 16:
            raise InvalidChecker("Too many checker functions")
        self.function_names = {name: f"fn_{i}" for i, name in enumerate(self.functions)}
        self.in_function = False
        self.serial = 0
        self.process = 0
        self.write_owners: dict[str, int] = {}
        self.private_bits = 0
        self.state_names: set[str] = set()
        self.reset_bits: dict[str, set[int]] = {}
        self.in_reset = False
        self.initialized: set[str] = set()
        self.symbols: dict[str, _Symbol] = {}
        self.assertions: dict[ET.Element, int] = {}
        self.flags: dict[int, bool] = {}
        self.instrumented = False
        self.sequential = False
        self.loop_work = 0
        self.loop_constants: dict[str, int] = {}
        self._validate_function_graph()

    def _validate_function_graph(self) -> None:
        for node in self.functions.values():
            if node.attrib.keys() - {"loc", "name", "dtype_id"}:
                raise InvalidChecker("Only native pure checker functions are supported")
            if not any(child.tag != "var" for child in node):
                raise InvalidChecker("Checker functions need a native executable body")

        def visit(name: str, active: set[str]) -> None:
            if name in active:
                raise InvalidChecker("Recursive functions are unsupported")
            if name not in self.functions:
                raise InvalidChecker("Function calls must name checker functions")
            for call in self.functions[name].iter("funcref"):
                visit(call.get("name", ""), active | {name})
        for name in self.functions:
            visit(name, set())

    def dtype(self, type_id: str) -> tuple[int, bool, int]:
        node = self.types.get(type_id)
        if node is None:
            raise InvalidChecker("Unknown checker type")
        if node.tag == "basicdtype" and node.get("name") in ("logic", "bit", "integer", "int"):
            width = abs(int(node.get("left", "0")) - int(node.get("right", "0"))) + 1
            if not 0 < width <= 256:
                raise InvalidChecker("Checker word width exceeds 256 bits")
            return width, node.get("signed") == "true", 1
        if node.tag == "unpackarraydtype":
            range_node = node.find("range")
            dims = list(range_node) if range_node is not None else []
            if len(dims) != 2:
                raise InvalidChecker("Unsupported observer array range")
            low, high = (_number(dim.get("name", "")) for dim in dims)
            if low != 0 or not 0 <= high < 64:
                raise InvalidChecker("Observer arrays must use [0:N] with at most 64 entries")
            width, signed, count = self.dtype(node.get("sub_dtype_id", ""))
            if count != 1:
                raise InvalidChecker("Use one unpacked array dimension")
            return width, signed, high + 1
        raise InvalidChecker(f"Unsupported checker type {node.tag}")

    def _lookup(self, name: str) -> _Symbol:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise InvalidChecker(f"Unknown or nonlocal variable {name}")

    def _declare(self, node: ET.Element, *, port: bool = False) -> str:
        original = node.get("name", "")
        if original.startswith(_PREFIX) or not original:
            raise InvalidChecker("Reserved checker identifier")
        if original in self.scopes[-1]:
            raise InvalidChecker("Duplicate variable declaration")
        width, signed, count = self.dtype(node.get("dtype_id", ""))
        if port:
            if node.get("dir") != "input" or count != 1 or original not in self.ports:
                raise InvalidChecker("Checker ports must be the exact DUT signals, all inputs")
            if self.ports[original][1] != width or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", original):
                raise InvalidChecker(f"Wrong checker port width for {original}")
            name = original
        else:
            name = f"v_{self.serial}"
            self.serial += 1
            self.private_bits += width * count
            if self.private_bits > MAX_PRIVATE_BITS:
                raise InvalidChecker("Checker private storage exceeds 4096 declared bits")
        symbol = _Symbol(name, node.get("dtype_id", ""), port,
                         node.get("param") == "true" or node.get("localparam") == "true",
                         self.in_function, len(self.scopes) > 1 and not self.in_function)
        self.scopes[-1][original] = symbol
        self.symbols[name] = symbol
        sign = " signed" if signed else ""
        packed = f" [{width - 1}:0]" if width > 1 else ""
        unpacked = f" [0:{count - 1}]" if count > 1 else ""
        if symbol.constant:
            if len(node) != 1 or node[0].tag != "const":
                raise InvalidChecker("Parameters must elaborate to integer constants")
            self.constants[name] = _number(node[0].get("name", ""))
            return f"localparam{sign}{packed} {name} = {node[0].get('name')};"
        if len(node):
            raise InvalidChecker("Declare checker monitor state without initializers")
        return f"{'input wire' if port else 'reg'}{sign}{packed} {name}{unpacked};"

    def _typed(self, node: ET.Element, text: str, *, unsigned: bool = False) -> str:
        width, signed, count = self.dtype(node.get("dtype_id", ""))
        if count != 1:
            raise InvalidChecker("Use an indexed observer array element")
        cast = "$signed" if signed and not unsigned else "$unsigned"
        return f"{cast}({width}'({text}))"

    def expr(self, node: ET.Element) -> str:
        tag, children = node.tag, list(node)
        if tag == "varref" and not children:
            symbol = self._lookup(node.get("name", ""))
            if self.sequential and symbol.temporary and symbol.name not in self.initialized:
                raise InvalidChecker("Clocked temporary variables must be assigned before use")
            if symbol.name in self.loop_constants:
                width, signed, _ = self.dtype(symbol.dtype)
                value = self.loop_constants[symbol.name] % (1 << width)
                return f"{width}'{'s' if signed else ''}h{value:x}"
            return symbol.name
        if tag == "const" and not children:
            _number(node.get("name", ""))
            return node.get("name", "")
        if tag in _BINARY and len(children) == 2:
            left, right = (self.expr(child) for child in children)
            if tag in ("lts", "ltes", "gts", "gtes", "shiftrs"):
                left, right = f"$signed({left})", f"$signed({right})"
            return self._typed(node, f"({left}) {_BINARY[tag]} ({right})")
        if tag in _UNARY and len(children) == 1:
            return self._typed(node, f"{_UNARY[tag]}({self.expr(children[0])})")
        if tag in ("extend", "extends") and len(children) == 1:
            cast = "$signed" if tag == "extends" else "$unsigned"
            return self._typed(node, f"{cast}({self.expr(children[0])})")
        if tag == "sel" and len(children) == 3:
            width = self.constant(children[2])
            if width != self.dtype(node.get("dtype_id", ""))[0]:
                raise InvalidChecker("Inconsistent packed selection")
            return self._typed(node, f"$unsigned({self.expr(children[0])}) >> ({self.expr(children[1])})",
                               unsigned=True)
        if tag == "arraysel" and len(children) == 2:
            if children[0].tag != "varref":
                raise InvalidChecker("Only local observer arrays can be indexed")
            symbol = self._lookup(children[0].get("name", ""))
            if self.dtype(symbol.dtype)[2] <= 1:
                raise InvalidChecker("Array selection requires an observer array")
            return f"{symbol.name}[{self.expr(children[1])}]"
        if tag == "cond" and len(children) == 3:
            condition, yes, no = (self.expr(child) for child in children)
            return self._typed(node, f"({condition}) ? ({yes}) : ({no})")
        if tag == "concat" and len(children) == 2:
            return self._typed(node, "{" + ", ".join(self.expr(child) for child in children) + "}")
        if tag == "replicate" and len(children) == 2:
            count = self.constant(children[1])
            if not 1 <= count <= 256:
                raise InvalidChecker("Invalid replication count")
            return self._typed(node, "{" + str(count) + "{" + self.expr(children[0]) + "}}")
        if tag == "funcref":
            name = node.get("name", "")
            if name not in self.functions or any(child.tag != "arg" or len(child) != 1 for child in children):
                raise InvalidChecker("Only pure checker function calls are supported")
            return self._typed(node, self.function_names[name] + "(" + ", ".join(
                self.expr(child[0]) for child in children) + ")")
        raise InvalidChecker(f"Unsupported expression {tag}")

    def constant(self, node: ET.Element, values: dict[str, int] | None = None) -> int:
        values = self.constants if values is None else values
        if node.tag == "const":
            return _number(node.get("name", ""))
        if node.tag == "varref":
            name = self._lookup(node.get("name", "")).name
            if name in values:
                return values[name]
        if node.tag in ("extend", "extends") and len(node) == 1:
            return self._constant_width(node, self.constant(node[0], values))
        if node.tag == "sel" and len(node) == 3:
            value, offset, width = (self.constant(child, values) for child in node)
            return (value >> offset) & ((1 << width) - 1)
        if node.tag in _BINARY and len(node) == 2:
            a, b = (self.constant(child, values) for child in node)
            operators = {"add": lambda: a + b, "sub": lambda: a - b, "mul": lambda: a * b,
                         "and": lambda: a & b, "or": lambda: a | b, "xor": lambda: a ^ b,
                         "lt": lambda: a < b, "lts": lambda: a < b,
                         "lte": lambda: a <= b, "ltes": lambda: a <= b,
                         "gt": lambda: a > b, "gts": lambda: a > b,
                         "gte": lambda: a >= b, "gtes": lambda: a >= b,
                         "eq": lambda: a == b, "neq": lambda: a != b}
            if node.tag in operators:
                return self._constant_width(node, int(operators[node.tag]()))
        raise InvalidChecker("Loop bounds and increments must be compile-time integers")

    def _constant_width(self, node: ET.Element, value: int) -> int:
        width, signed, _ = self.dtype(node.get("dtype_id", ""))
        value %= 1 << width
        return value - (1 << width) if signed and value & (1 << (width - 1)) else value

    def _target(self, node: ET.Element) -> tuple[str, _Symbol]:
        if node.tag == "varref":
            symbol = self._lookup(node.get("name", ""))
            return symbol.name, symbol
        if node.tag in ("sel", "arraysel") and len(node) >= 2:
            base, symbol = self._target(node[0])
            if node.tag == "arraysel":
                return f"{base}[{self.expr(node[1])}]", symbol
            width = self.constant(node[2])
            return f"{base}[{self.expr(node[1])} +: {width}]", symbol
        raise InvalidChecker("Assignment requires a local checker variable")

    def _assignment(self, node: ET.Element) -> str:
        if len(node) != 2:
            raise InvalidChecker("Malformed assignment")
        lhs, symbol = self._target(node[1])
        if symbol.input_port or symbol.constant or (self.in_function and not symbol.function_local):
            raise InvalidChecker("Checker may write only its private monitor state")
        if self.sequential and not self.in_function:
            if node.tag == "assign" and not symbol.temporary:
                raise InvalidChecker("Use nonblocking assignments for persistent monitor registers")
            if node.tag == "assigndly" and symbol.temporary:
                raise InvalidChecker("Declare persistent monitor registers at module scope")
            if symbol.temporary and node[1].tag != "varref":
                raise InvalidChecker("Assign a clocked temporary completely before using it")
        rhs = self.expr(node[0])
        self.initialized.add(symbol.name)
        if not self.in_function:
            owner = self.write_owners.setdefault(symbol.name, self.process)
            if owner != self.process:
                raise InvalidChecker("Each checker variable must have a single writer")
            if self.sequential:
                if node.tag == "assigndly":
                    self.state_names.add(symbol.name)
                    if self.in_reset:
                        bits = self._reset_target_bits(node[1])
                        self.reset_bits.setdefault(symbol.name, set()).update(bits)
        if node.tag == "assigndly" and (not self.sequential or self.in_function):
            raise InvalidChecker("Nonblocking assignments require the checker clock")
        try:
            self.constants[symbol.name] = self.constant(node[0])
        except InvalidChecker:
            self.constants.pop(symbol.name, None)
        operator = "<=" if node.tag == "assigndly" else "="
        return f"{lhs} {operator} {rhs};"

    def _reset_target_bits(self, node: ET.Element) -> set[int]:
        _, symbol = self._target(node)
        width, _, count = self.dtype(symbol.dtype)
        if node.tag == "varref":
            return set(range(width * count))
        if node.tag == "arraysel" and node[0].tag == "varref":
            index = self.constant(node[1])
            if not 0 <= index < count:
                raise InvalidChecker("Reset array index is outside its declared range")
            return set(range(index * width, (index + 1) * width))
        if node.tag == "sel" and node[0].tag == "varref":
            start, selected = self.constant(node[1]), self.constant(node[2])
            if not 0 <= start < start + selected <= width:
                raise InvalidChecker("Reset bit selection is outside its declared range")
            return set(range(start, start + selected))
        raise InvalidChecker("Use complete monitor reset assignments with constant indices")

    def _reset_condition(self, node: ET.Element) -> bool | None:
        if node.tag == "varref" and node.get("name") == self.reset:
            return True
        if node.tag in ("not", "lognot") and len(node) == 1:
            if node[0].tag == "varref" and node[0].get("name") == self.reset:
                return False
        return None

    def _bare_assertion(self, node: ET.Element) -> ET.Element | None:
        if node.tag != "if" or len(node) != 2 or node[0].tag != "cexpr":
            return None
        if len(node[0]) != 1 or node[0][0].tag != "text" or node[0][0].attrib.keys() - {"loc"}:
            raise InvalidChecker("Unsupported generated assertion guard")
        loc = node.get("loc", "").split(",")
        if len(loc) != 5:
            raise InvalidChecker("Assertion source location is unavailable")
        lines = self.code.splitlines(keepends=True)
        line, column = int(loc[1]), int(loc[2])
        offset = sum(map(len, lines[:line - 1])) + column - 1
        token_index = next((i for i, (_, start) in enumerate(self.tokens) if start == offset), None)
        if token_index is None or self.tokens[token_index][0] != "assert":
            raise InvalidChecker("Only native immediate assertions are supported")
        tokens = [text for text, _ in self.tokens[token_index + 1:]]
        if not tokens or tokens[0] != "(":
            raise InvalidChecker("Use assert(expression) without an action block")
        depth = 0
        end = None
        for i, token in enumerate(tokens):
            depth += token == "("
            depth -= token == ")"
            if depth == 0:
                end = i
                break
        if end is None or tokens[end + 1:end + 2] != [";"]:
            raise InvalidChecker("Assertion action blocks are unsupported")
        body = node[1]
        if (body.tag == "begin" and [child.tag for child in body] == ["display", "stop"]
                and all(child.get("loc") == node.get("loc") for child in body)):
            return ET.Element("const", name="1'h1", dtype_id=node[0].get("dtype_id", ""))
        if body.tag != "begin" or len(body) != 1 or body[0].tag != "if" or len(body[0]) != 2:
            raise InvalidChecker("Unsupported immediate assertion form")
        inner = body[0]
        fail = inner[1]
        if (fail.tag != "begin" or [child.tag for child in fail] != ["display", "stop"]
                or any(child.get("loc") != node.get("loc") for child in fail)):
            raise InvalidChecker("Only an assertion's native failure action is supported")
        return inner[0]

    def statement(self, node: ET.Element) -> str:
        predicate = self._bare_assertion(node)
        if predicate is not None:
            if self.in_function:
                raise InvalidChecker("Place assertions in observer processes")
            index = self.assertions.setdefault(node, len(self.assertions))
            if len(self.assertions) > MAX_ASSERTIONS:
                raise InvalidChecker("Too many checker assertions")
            self.flags[index] = self.sequential
            failure = self.expr(predicate)
            if not self.instrumented:
                return f"assert (!({failure}));"
            operator = "<=" if self.sequential else "="
            return f"if (({failure}) !== 1'b0) {_PREFIX}a{index} {operator} 1'b1;"
        if node.tag == "begin":
            self.scopes.append({})
            statements = [self._declare(child) if child.tag == "var" else self.statement(child)
                          for child in node]
            self.scopes.pop()
            return "begin\n" + "\n".join(statements) + "\nend"
        if node.tag in ("assign", "assigndly"):
            return self._assignment(node)
        if node.tag == "if" and len(node) in (2, 3):
            condition = self.expr(node[0])
            before = dict(self.constants)
            before_initialized = set(self.initialized)
            before_reset = self.in_reset
            before_bits = {name: set(bits) for name, bits in self.reset_bits.items()}
            reset_branch = self._reset_condition(node[0])
            self.in_reset = before_reset or reset_branch is True
            yes = self.statement(node[1])
            yes_constants = dict(self.constants)
            yes_initialized = set(self.initialized)
            yes_bits = self.reset_bits
            self.constants = dict(before)
            self.initialized = set(before_initialized)
            self.reset_bits = {name: set(bits) for name, bits in before_bits.items()}
            self.in_reset = before_reset or reset_branch is False
            no = " else " + self.statement(node[2]) if len(node) == 3 else ""
            self.constants = {name: value for name, value in yes_constants.items()
                              if self.constants.get(name) == value}
            self.initialized &= yes_initialized
            no_bits = self.reset_bits
            if reset_branch is True:
                self.reset_bits = yes_bits
            elif reset_branch is False:
                self.reset_bits = no_bits
            else:
                self.reset_bits = {name: bits & no_bits.get(name, set()) for name, bits in yes_bits.items()}
            self.in_reset = before_reset
            return f"if ({condition}) {yes}{no}"
        if node.tag == "case" and len(node):
            if node.attrib.keys() - {"loc"}:
                raise InvalidChecker("Only ordinary case statements are supported")
            condition = self.expr(node[0])
            items = []
            before = dict(self.constants)
            before_initialized = set(self.initialized)
            before_bits = {name: set(bits) for name, bits in self.reset_bits.items()}
            branches = []
            initialized_branches = []
            reset_branches = []
            has_default = False
            for item in list(node)[1:]:
                self.constants = dict(before)
                self.initialized = set(before_initialized)
                self.reset_bits = {name: set(bits) for name, bits in before_bits.items()}
                if item.tag != "caseitem":
                    raise InvalidChecker("Unsupported case construct")
                labels, statements = [], []
                for child in item:
                    if child.tag == "const":
                        labels.append(self.expr(child))
                    else:
                        statements.append(self.statement(child))
                label = ", ".join(labels) if labels else "default"
                has_default |= not labels
                branches.append(dict(self.constants))
                initialized_branches.append(set(self.initialized))
                reset_branches.append(self.reset_bits)
                items.append(label + ": begin\n" + "\n".join(statements) + "\nend")
            if not has_default:
                branches.append(before)
                initialized_branches.append(before_initialized)
                reset_branches.append(before_bits)
            self.constants = {name: value for name, value in before.items()
                              if all(branch.get(name) == value for branch in branches)}
            self.initialized = set.intersection(*initialized_branches)
            self.reset_bits = {
                name: set.intersection(*(branch.get(name, set()) for branch in reset_branches))
                for name in set().union(*(branch.keys() for branch in reset_branches))
            }
            return f"case ({condition})\n" + "\n".join(items) + "\nendcase"
        if node.tag == "while":
            return self._loop(node)
        raise InvalidChecker(f"Unsupported statement {node.tag}")

    def _loop(self, node: ET.Element) -> str:
        if (len(node) != 4 or any(child.tag != "begin" for child in node)
                or len(node[0]) or len(node[1]) != 1 or len(node[3]) != 1):
            raise InvalidChecker("Use a constant-bounded for loop")
        increment = node[3][0]
        if increment.tag != "assign" or len(increment) != 2 or increment[1].tag != "varref":
            raise InvalidChecker("Loop counter requires a constant increment")
        symbol = self._lookup(increment[1].get("name", ""))
        for assignment in node[2].iter():
            if assignment.tag in ("assign", "assigndly") and len(assignment) == 2:
                if self._target(assignment[1])[1] == symbol:
                    raise InvalidChecker("Loop body cannot modify its counter")
        values = dict(self.constants)
        if symbol.name not in values:
            raise InvalidChecker("Loop counter must have a constant initializer")
        start = values[symbol.name]
        iterations = []
        while self.constant(node[1][0], values):
            iterations.append(values[symbol.name])
            values[symbol.name] = self.constant(increment[0], values)
            if len(iterations) > MAX_LOOP_STEPS:
                raise InvalidChecker("Checker loop exceeds 128 iterations")
        self.loop_work += len(iterations)
        if self.loop_work > 1024:
            raise InvalidChecker("Checker loops exceed the total work limit")
        self.constants[symbol.name] = start
        bodies = []
        for value in iterations:
            self.loop_constants[symbol.name] = value
            self.constants[symbol.name] = value
            bodies.append(self.statement(node[2]))
        self.loop_constants.pop(symbol.name, None)
        final_value = values[symbol.name]
        self.constants[symbol.name] = final_value
        bodies.append(f"{symbol.name} = {final_value};")
        return "begin\n" + "\n".join(bodies) + "\nend"

    def _function(self, node: ET.Element) -> str:
        self.in_function = True
        self.scopes.append({})
        width, signed, count = self.dtype(node.get("dtype_id", ""))
        if count != 1:
            raise InvalidChecker("Functions must return packed integers")
        declarations, statements, args = [], [], []
        for child in node:
            if child.tag == "var":
                declaration = self._declare(child)
                symbol = self._lookup(child.get("name", ""))
                if child.get("dir") == "output":
                    symbol.name = self.function_names[node.get("name", "")]
                elif child.get("dir") == "input":
                    args.append(declaration.replace("reg", "input", 1))
                else:
                    declarations.append(declaration)
            else:
                statements.append(self.statement(child))
        self.scopes.pop()
        self.in_function = False
        sign = " signed" if signed else ""
        return (f"function automatic{sign} [{width - 1}:0] {self.function_names[node.get('name', '')]}"
                f"({', '.join(arg.rstrip(';') for arg in args)});\n" + "\n".join(declarations)
                + "\nbegin\n" + "\n".join(statements) + "\nend\nendfunction")

    def render(self, instrumented: bool = False) -> str:
        self.instrumented = instrumented
        declarations, processes = [], []
        port_nodes = [node for node in self.module.findall("var") if node.get("dir")]
        if {node.get("name") for node in port_nodes} != set(self.ports):
            raise InvalidChecker("Checker ports must be the exact DUT signals, all inputs")
        for node in self.module.findall("var"):
            declarations.append(self._declare(node, port=node.get("dir") is not None))
        for node in self.module:
            if node.tag == "var":
                continue
            if node.tag == "func":
                processes.append(self._function(node))
                continue
            self.process += 1
            before = len(self.assertions)
            if node.tag == "contassign":
                processes.append("assign " + self._assignment(node))
                continue
            if node.tag != "always":
                raise InvalidChecker(f"Unsupported observer member {node.tag}")
            children = list(node)
            self.sequential = bool(children and children[0].tag == "sentree")
            event = "@*"
            if self.sequential:
                tree = children.pop(0)
                if (self.clock is None or len(tree) != 1 or tree[0].tag != "senitem"
                        or tree[0].get("edgeType") != "POS" or len(tree[0]) != 1
                        or tree[0][0].tag != "varref" or tree[0][0].get("name") != self.clock):
                    raise InvalidChecker("Stateful observers must use only posedge of the task clock")
                event = f"@(posedge {self.clock})"
            statements = [self.statement(child) for child in children]
            if instrumented and not self.sequential:
                defaults = [f"{_PREFIX}a{i} = 1'b0;" for i in range(before, len(self.assertions))]
                statements = defaults + statements
            processes.append(f"always {event} begin\n" + "\n".join(statements) + "\nend")
            self.sequential = False
        if not self.assertions:
            raise InvalidChecker("Checker must contain a retained immediate assertion")
        for name in self.state_names:
            width, _, count = self.dtype(self.symbols[name].dtype)
            if self.reset is None or self.reset_bits.get(name) != set(range(width * count)):
                raise InvalidChecker("Every clocked monitor register must reset through if (rst)")
        port_names = list(self.ports)
        if instrumented:
            port_names.append(_PREFIX + "fail")
            declarations.append(f"output wire {_PREFIX}fail;")
            for index, sequential in self.flags.items():
                declarations.append(f"reg {_PREFIX}a{index};")
                if sequential:
                    processes.append(f"initial {_PREFIX}a{index} = 1'b0;")
            processes.append(f"assign {_PREFIX}fail = " + " | ".join(
                f"{_PREFIX}a{index}" for index in self.flags) + ";")
        return "module rtl_checker (" + ", ".join(port_names) + ");\n" + "\n".join(
            [*declarations, *processes]) + "\nendmodule\n"


def validate_checker(code: str, ports: dict[str, tuple[str, int]], workdir: Path,
                     clock: str | None = None, reset: str | None = None) -> CheckerValidation:
    """Return native assertion HDL and an instrumented simulation observer.

    ``ports`` names the observed DUT interface, with its original direction and
    width. Every checker port is an input. ``reset`` identifies a DUT signal;
    monitor history must explicitly reset using that signal in submitted code.
    """
    try:
        if len(code.encode("utf-8")) > MAX_SOURCE_BYTES:
            raise InvalidChecker("Checker source exceeds 64 KiB")
        _tokens(code)
        if clock is not None and (clock not in ports or ports[clock][1] != 1):
            raise InvalidChecker("Task clock is not a scalar interface signal")
        if reset is not None and (reset not in ports or ports[reset][1] != 1):
            raise InvalidChecker("Task reset is not a scalar interface signal")
        workdir.mkdir(parents=True, exist_ok=True)
        source, xml = workdir / "rtl_checker.sv", workdir / "checker.xml"
        source.write_text(_without_comments(code), encoding="utf-8")
        xml.unlink(missing_ok=True)
        result = run(["verilator", "--xml-only", "--assert", "--language", "1800-2012",
                      "-Wall", "-Wno-fatal", "--top-module", "rtl_checker", "--xml-output",
                      str(xml), str(source)], cwd=workdir, timeout_s=15)
        if not result.ok or not xml.is_file():
            if result.timed_out or result.returncode in (-9, -24, -25):
                return CheckerValidation(False, reason="Native checker validation hit a resource limit",
                                         inconclusive=True)
            raise InvalidChecker("Native checker validation failed. " + tail(result.log, 1600))
        if any(f"%Warning-{name}:" in result.log for name in ("LATCH", "MULTIDRIVEN", "UNDRIVEN")):
            raise InvalidChecker("Observer has incomplete combinational assignments or multiple drivers")
        if xml.stat().st_size > MAX_XML_BYTES:
            raise InvalidChecker("Checker XML exceeds the size limit")
        document = ET.parse(xml).getroot()
        if len(list(document.iter())) > MAX_NODES:
            raise InvalidChecker("Checker AST exceeds the node limit")
        source_id = next((node.get("id") for node in document.findall("./files/file")
                          if Path(node.get("filename", "")).resolve() == source.resolve()), None)
        if source_id is None:
            raise InvalidChecker("Checker source provenance is unavailable")
        for node in document.findall("./module_files/file"):
            if node.get("id") != source_id:
                raise InvalidChecker("Checker must be self-contained")
        for module in document.findall("./netlist/module"):
            for node in module.iter():
                if node.get("loc") and node.get("loc", "").split(",")[0] != source_id:
                    raise InvalidChecker("Observer AST contains code from another source")
        native = _Renderer(document, code, ports, clock, reset)
        regenerated = native.render()
        monitor = _Renderer(document, code, ports, clock, reset)
        instrumented = monitor.render(instrumented=True)
        if max(len(regenerated.encode()), len(instrumented.encode())) > 1024 * 1024:
            raise InvalidChecker("Expanded checker exceeds 1 MiB")
        state_bits = sum(native.dtype(native.symbols[name].dtype)[0]
                         * native.dtype(native.symbols[name].dtype)[2] for name in native.state_names)
        return CheckerValidation(True, source=regenerated, instrumented=instrumented,
                                 assert_count=len(native.assertions), state_bits=state_bits)
    except (InvalidChecker, OSError, ET.ParseError, ValueError, TypeError, KeyError) as exc:
        return CheckerValidation(False, reason=str(exc))
