#!/usr/bin/env python
import sys
from core.readiness_gate import run_readiness_check


def main():
    payload = run_readiness_check(write_log=True)
    if payload["ready"]:
        print("READY")
        return 0
    print("NOT_READY")
    print("Reasons:", ",".join(payload.get("reasons") or []))
    if payload.get("warnings"):
        print("Warnings:", ",".join(payload.get("warnings") or []))
    return 2


if __name__ == "__main__":
    sys.exit(main())
