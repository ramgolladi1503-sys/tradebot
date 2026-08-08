#!/usr/bin/env python3
"""Safe launcher for the S003 autonomous cycle.

The v1 cycle historically merged child stderr into stdout. Git can emit benign
warnings (for example, "Empty last update token") on stderr while
`git status --porcelain` correctly emits an empty stdout for a clean checkout.
Merging the streams therefore created a false AUTHORITY_WORKTREE_NOT_CLEAN hard
stop. This wrapper preserves the established cycle logic and changes only the
subprocess stream contract so machine-readable stdout remains authoritative.
"""
from __future__ import annotations

import subprocess

import mros_autonomous_cycle as cycle


def safe_run(cwd, *args: str, timeout: int = 1200, check: bool = True):
    p = subprocess.run(
        list(args),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and p.returncode != 0:
        detail = (p.stderr or p.stdout or "")[-4000:]
        raise cycle.CycleError(f"COMMAND_FAILED:{' '.join(args)}:{detail}")
    return p


def main() -> int:
    # Patch only process I/O semantics. All S003 state, review, repair,
    # calibration, audit, and authority logic remains in the established cycle.
    cycle.run = safe_run
    result = cycle.main()
    return 0 if result is None else int(result)


if __name__ == "__main__":
    raise SystemExit(main())
