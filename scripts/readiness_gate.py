#!/usr/bin/env python
from pathlib import Path
import runpy
import sys

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from core.readiness_gate import run_readiness_check


def main():
    payload = run_readiness_check(write_log=True)
    if payload.get("can_trade"):
        print(f"READY state={payload.get('state')}")
        return 0
    print(f"NOT_READY state={payload.get('state')}")
    print("Reasons:", ",".join(payload.get("blockers") or payload.get("reasons") or []))
    if payload.get("warnings"):
        print("Warnings:", ",".join(payload.get("warnings") or []))
    return 2


if __name__ == "__main__":
    sys.exit(main())
