"""Load a capability policy for a Watt module."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PolicyError(Exception):
    pass


@dataclass
class Preopen:
    fd: int
    guest: str
    host: str


@dataclass
class Policy:
    fuel: int
    max_pages: int
    max_stack: int
    preopens: list[Preopen]
    allow_grow: bool
    allow_indirect: bool
    allow_start_export: bool
    host_root: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "fuel": self.fuel,
            "max_pages": self.max_pages,
            "max_stack": self.max_stack,
            "preopens": [{"fd": p.fd, "guest": p.guest, "host": p.host} for p in self.preopens],
            "allow_grow": self.allow_grow,
            "allow_indirect": self.allow_indirect,
            "allow_start_export": self.allow_start_export,
        }


def load_policy(path: str | Path) -> Policy:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(str(exc)) from exc
    if not isinstance(raw, dict):
        raise PolicyError("policy must be an object")
    preopens = []
    for item in raw.get("preopens", []):
        preopens.append(Preopen(int(item["fd"]), str(item["guest"]), str(item["host"])))
    return Policy(
        fuel=int(raw.get("fuel", 100000)),
        max_pages=int(raw.get("max_pages", 1)),
        max_stack=int(raw.get("max_stack", 256)),
        preopens=preopens,
        allow_grow=bool(raw.get("allow_grow", False)),
        allow_indirect=bool(raw.get("allow_indirect", True)),
        allow_start_export=bool(raw.get("allow_start_export", False)),
        host_root=raw.get("host_root"),
    )
