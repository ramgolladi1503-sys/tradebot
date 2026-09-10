#!/usr/bin/env python3
"""Create a fresh external premarket root and emit bounded preflight evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from core.morning_session_root import SessionRootError, create_session_root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    clean = not subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
    result = {
        "release_sha_requested": args.release,
        "release_sha_actual": actual,
        "release_sha_match": actual == args.release,
        "worktree_clean": clean,
        "fresh_root": None,
        "preflight_pass": False,
        "read_only": True,
        "broker_write_authority": False,
        "order_authority": False,
        "orders_placed": 0,
    }
    try:
        if not result["release_sha_match"] or not clean:
            raise SessionRootError("release_authority_or_clean_tree_failed")
        result["fresh_root"] = create_session_root(external_root=args.external_root, session_date=args.session_date, release_sha=args.release)
        result["preflight_pass"] = True
    except (SessionRootError, subprocess.CalledProcessError) as exc:
        result["blocker"] = str(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["preflight_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
