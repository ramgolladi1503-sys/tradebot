#!/usr/bin/env python3
"""Permanent operator entrypoint for one canonical read-only live session."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from core.read_only_live_pipeline import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-date", default=date.today().isoformat())
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--token-path", required=True, type=Path)
    parser.add_argument("--subscription-token", action="append", type=int, required=True)
    parser.add_argument("--max-runtime-sec", type=float)
    args = parser.parse_args()
    return run_pipeline(
        session_date=args.session_date, runtime_root=args.runtime_root,
        token_path=args.token_path, subscription_tokens=args.subscription_token,
        max_runtime_sec=args.max_runtime_sec,
    )


if __name__ == "__main__":
    raise SystemExit(main())

