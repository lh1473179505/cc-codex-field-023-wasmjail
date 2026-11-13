"""CLI. inspect already works; run is the piece to implement."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from wasmjail.assemble import AsmError, load_module
from wasmjail.policy import PolicyError, load_policy


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wasmjail")
    sub = p.add_subparsers(dest="cmd", required=True)

    ins = sub.add_parser("inspect", help="assemble a Watt module and show its IR")
    ins.add_argument("--module", required=True)
    ins.add_argument("--policy", required=False)

    run = sub.add_parser("run", help="instantiate a module and invoke an export")
    run.add_argument("--module", required=True)
    run.add_argument("--policy", required=True)
    run.add_argument("--invoke", required=True)
    run.add_argument("--arg", action="append", default=[], help="i32 argument, may be repeated")
    run.add_argument("--host-root", required=False, default=".", help="base directory for preopen host paths")
    run.add_argument("--report", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        module = load_module(args.module)
    except (OSError, AsmError) as exc:
        print(f"failed to assemble module: {exc}", file=sys.stderr)
        return 2

    policy = None
    if getattr(args, "policy", None):
        try:
            policy = load_policy(args.policy)
        except (PolicyError, OSError) as exc:
            print(f"failed to load policy: {exc}", file=sys.stderr)
            return 2

    if args.cmd == "inspect":
        payload = {"module": module.as_dict()}
        if policy is not None:
            payload["policy"] = policy.as_dict()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "run":
        from wasmjail.engine import run_module

        try:
            argv_i32 = [int(a, 0) for a in args.arg]
        except ValueError as exc:
            print(f"bad --arg: {exc}", file=sys.stderr)
            return 2
        try:
            report = run_module(module, policy, args.invoke, argv_i32, args.host_root)
        except NotImplementedError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        decision = str(report.get("decision", "")).lower()
        if decision == "allow":
            return 0
        if decision == "deny":
            return 1
        print("report is missing a decision of allow or deny", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
