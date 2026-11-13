"""Assemble a tiny Watt module (text) into IR.

This format is intentionally smaller than WebAssembly text, but the runtime
still has to honour fuel, memory, types, start, and host capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


class AsmError(Exception):
    pass


@dataclass
class FuncType:
    params: list[str]
    results: list[str]


@dataclass
class Func:
    name: str
    type: FuncType
    locals: list[str]
    body: list[dict]


@dataclass
class ImportFunc:
    module: str
    name: str
    type: FuncType


@dataclass
class DataSeg:
    offset: int
    bytes: bytes

    def as_dict(self) -> dict[str, Any]:
        return {"offset": self.offset, "hex": self.bytes.hex()}


@dataclass
class Module:
    memory_pages: int = 1
    funcs: dict[str, Func] = field(default_factory=dict)
    func_order: list[str] = field(default_factory=list)
    imports: dict[str, ImportFunc] = field(default_factory=dict)
    exports: dict[str, str] = field(default_factory=dict)
    start: str | None = None
    data: list[DataSeg] = field(default_factory=list)
    table: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "memory_pages": self.memory_pages,
            "imports": {
                k: {"module": v.module, "name": v.name, "params": v.type.params, "results": v.type.results}
                for k, v in self.imports.items()
            },
            "funcs": {
                k: {
                    "params": f.type.params,
                    "results": f.type.results,
                    "locals": f.locals,
                    "body": f.body,
                }
                for k, f in self.funcs.items()
            },
            "func_order": self.func_order,
            "exports": self.exports,
            "start": self.start,
            "data": [d.as_dict() for d in self.data],
            "table": self.table,
        }


def assemble(text: str) -> Module:
    lines = text.splitlines()
    mod = Module()
    i = 0
    current: Func | None = None
    pending_if: list[str] = []

    def tokens(s: str) -> list[str]:
        out: list[str] = []
        buf = ""
        in_str = False
        for ch in s:
            if in_str:
                buf += ch
                if ch == '"':
                    out.append(buf)
                    buf = ""
                    in_str = False
                continue
            if ch == '"':
                if buf:
                    out.append(buf)
                    buf = ""
                buf = '"'
                in_str = True
                continue
            if ch.isspace():
                if buf:
                    out.append(buf)
                    buf = ""
                continue
            buf += ch
        if in_str:
            raise AsmError("unterminated string")
        if buf:
            out.append(buf)
        return out

    def parse_type_sig(ts: list[str], start: int) -> tuple[FuncType, int]:
        params: list[str] = []
        results: list[str] = []
        j = start
        while j < len(ts):
            if ts[j] == "(param":
                j += 1
                while j < len(ts) and not ts[j].endswith(")"):
                    params.append(_ty(ts[j]))
                    j += 1
                if j >= len(ts):
                    raise AsmError("bad param list")
                last = ts[j][:-1] if ts[j].endswith(")") else ""
                if last:
                    params.append(_ty(last))
                j += 1
                continue
            if ts[j].startswith("(param"):
                raise AsmError("bad param")
            if ts[j] == "(result":
                j += 1
                while j < len(ts) and not ts[j].endswith(")"):
                    results.append(_ty(ts[j]))
                    j += 1
                if j >= len(ts):
                    raise AsmError("bad result list")
                last = ts[j][:-1] if ts[j].endswith(")") else ""
                if last:
                    results.append(_ty(last))
                j += 1
                continue
            break
        return FuncType(params, results), j

    def _ty(s: str) -> str:
        if s not in {"i32"}:
            raise AsmError(f"unsupported type {s}")
        return s

    def emit(op: dict) -> None:
        if current is None:
            raise AsmError(f"instruction outside function: {op}")
        current.body.append(op)

    while i < len(lines):
        raw = lines[i].split("#", 1)[0].strip()
        i += 1
        if not raw:
            continue
        ts = tokens(raw)
        head = ts[0]
        if current is None:
            if head == "memory":
                if len(ts) != 2:
                    raise AsmError("memory <pages>")
                mod.memory_pages = int(ts[1])
            elif head == "import":
                # import host path_open (param i32 i32) (result i32)
                if len(ts) < 3:
                    raise AsmError("import")
                module, name = ts[1], ts[2]
                typ, _ = parse_type_sig(ts, 3)
                key = f"{module}.{name}"
                if key in mod.imports or name in mod.funcs:
                    raise AsmError("duplicate import")
                mod.imports[name] = ImportFunc(module, name, typ)
            elif head == "func":
                if len(ts) < 2:
                    raise AsmError("func")
                name = ts[1]
                typ, _ = parse_type_sig(ts, 2)
                current = Func(name=name, type=typ, locals=[], body=[])
            elif head == "export":
                if len(ts) != 3:
                    raise AsmError("export <export-name> <func-name>")
                mod.exports[ts[1]] = ts[2]
            elif head == "start":
                if len(ts) != 2:
                    raise AsmError("start <func>")
                mod.start = ts[1]
            elif head == "table":
                # table f1 f2 f3
                mod.table = ts[1:]
            elif head == "data":
                # data <offset> "bytes"  or data <offset> hex:DEAD
                if len(ts) != 3:
                    raise AsmError("data")
                off = int(ts[1], 0)
                if ts[2].startswith("hex:"):
                    b = bytes.fromhex(ts[2][4:])
                elif ts[2].startswith('"') and ts[2].endswith('"'):
                    b = bytes(ts[2][1:-1], "utf-8")
                else:
                    raise AsmError("data payload")
                mod.data.append(DataSeg(off, b))
            else:
                raise AsmError(f"unknown top-level {head}")
            continue

        # inside function
        if head == "end" and not pending_if and not any(op.get("op") in {"block", "loop", "if"} and False for op in []):
            # We use explicit end for if/block/loop as well; a bare end that
            # closes the function is only allowed when body nesting is 0.
            depth = _nest_depth(current.body)
            if depth == 0:
                if current.name in mod.funcs or current.name in mod.imports:
                    raise AsmError("duplicate func")
                mod.funcs[current.name] = current
                mod.func_order.append(current.name)
                current = None
            else:
                emit({"op": "end"})
            continue
        if head == "end":
            emit({"op": "end"})
            continue
        if head == "local":
            for t in ts[1:]:
                current.locals.append(_ty(t))
            continue
        if head == "i32.const":
            emit({"op": "i32.const", "value": _i32(ts[1])})
        elif head in {"local.get", "local.set", "local.tee"}:
            emit({"op": head, "index": int(ts[1])})
        elif head in {
            "i32.add", "i32.sub", "i32.mul", "i32.div_s", "i32.eqz",
            "i32.eq", "i32.ne", "i32.lt_s", "i32.gt_s", "i32.le_s", "i32.ge_s",
            "i32.and", "i32.or", "i32.xor", "drop", "return", "memory.grow",
            "i32.load", "i32.store", "else", "unreachable",
        }:
            emit({"op": head})
        elif head in {"if", "block", "loop"}:
            emit({"op": head})
        elif head in {"br", "br_if"}:
            emit({"op": head, "label": int(ts[1])})
        elif head == "call":
            emit({"op": "call", "target": ts[1]})
        elif head == "call_indirect":
            # call_indirect (param ...) (result ...)   type taken from tokens
            typ, _ = parse_type_sig(ts, 1)
            emit({"op": "call_indirect", "params": typ.params, "results": typ.results})
        else:
            raise AsmError(f"unknown op {head}")

    if current is not None:
        raise AsmError("unclosed function")
    return mod


def _nest_depth(body: list[dict]) -> int:
    depth = 0
    for op in body:
        if op["op"] in {"if", "block", "loop"}:
            depth += 1
        elif op["op"] == "end":
            depth -= 1
    return depth


def _i32(s: str) -> int:
    n = int(s, 0)
    # store as signed 32-bit
    n &= 0xFFFFFFFF
    if n >= 0x80000000:
        n -= 0x100000000
    return n


def load_module(path: str | Path) -> Module:
    text = Path(path).read_text(encoding="utf-8")
    return assemble(text)
