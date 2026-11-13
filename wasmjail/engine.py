"""Watt runtime. Not implemented in this snapshot."""

from __future__ import annotations

from typing import Any

from wasmjail.assemble import Module
from wasmjail.policy import Policy


def run_module(
    module: Module,
    policy: Policy,
    invoke: str,
    args: list[int],
    host_root: str,
) -> dict[str, Any]:
    raise NotImplementedError("run_module is not implemented in this snapshot")
