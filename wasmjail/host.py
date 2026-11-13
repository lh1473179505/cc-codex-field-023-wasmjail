"""Host import ABI and path helpers.

The runtime must call these helpers when a module invokes an import. Do not
give a module a host file descriptor that was opened under a different
module's preopens. The helpers below do not themselves enforce policy; they
only parse guest strings out of memory and do lexical path work.
"""

from __future__ import annotations

from pathlib import PurePosixPath


class HostError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


def read_guest_bytes(memory: bytearray, ptr: int, length: int) -> bytes:
    if ptr < 0 or length < 0 or ptr + length > len(memory):
        raise HostError("mem_out_of_bounds")
    return bytes(memory[ptr:ptr + length])


def write_guest_bytes(memory: bytearray, ptr: int, data: bytes) -> None:
    if ptr < 0 or ptr + len(data) > len(memory):
        raise HostError("mem_out_of_bounds")
    memory[ptr:ptr + len(data)] = data


def decode_guest_path(raw: bytes) -> str:
    if b"\x00" in raw:
        raise HostError("bad_path")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HostError("bad_path") from exc


def lexical_join(guest_root: str, rel: str) -> str:
    """Join a guest preopen root and a relative path without following host links.

    The result is a POSIX-style guest path. Rejection of escapes is left to
    the runtime (it must compare the normalized result with the root).
    """
    if rel.startswith("/") or rel.startswith("\\"):
        base = PurePosixPath("/")
        path = PurePosixPath(rel)
        # absolute guest paths are still interpreted against /
        parts = path.parts[1:]
        cur = base
    else:
        cur = PurePosixPath(guest_root)
        parts = PurePosixPath(rel).parts
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if cur == PurePosixPath(guest_root) or cur == PurePosixPath("/"):
                # leave the path at root; runtime should still deny if this
                # would walk out of the granted preopen.
                continue
            cur = cur.parent
            continue
        cur = cur / part
    return cur.as_posix()
