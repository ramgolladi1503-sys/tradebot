#!/usr/bin/env python3
"""Single command surface for governed Morning Readiness operations."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from core.morning_session_root import SessionRootError, create_session_root
from core.morning_operator_status import build_status


def preflight(args: argparse.Namespace) -> int:
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    clean = not subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
    result = {"release_sha_actual": actual, "release_sha_match": actual == args.release, "worktree_clean": clean, "preflight_pass": False}
    try:
        if actual != args.release or not clean:
            raise SessionRootError("release_authority_or_clean_tree_failed")
        result["session_root"] = create_session_root(external_root=args.external_root, session_date=args.session_date, release_sha=args.release)
        result["preflight_pass"] = True
    except SessionRootError as exc:
        result["blocker"] = str(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["preflight_pass"] else 2


def observer(args: argparse.Namespace) -> int:
    command = [sys.executable, "scripts/morning_readonly_observer.py", "--launch-plan", str(args.launch_plan), "--session-root", str(args.session_root), "--token-path", str(args.token_path), "--session-date", args.session_date]
    if args.max_runtime_sec is not None:
        command.extend(["--max-runtime-sec", str(args.max_runtime_sec)])
    supervisor = [sys.executable, "scripts/morning_observer_supervisor.py", "--status", str(args.status), "--", *command]
    return subprocess.call(supervisor)


def status(args: argparse.Namespace) -> int:
    payload = json.loads(args.status.read_text(encoding="utf-8")) if args.status.exists() else build_status(state="FAIL_CLOSED", release_sha=args.release, blockers=["status_missing"])
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="tradebot-morning-readiness")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("preflight"); p.add_argument("--release", required=True); p.add_argument("--session-date", required=True); p.add_argument("--external-root", type=Path, required=True); p.add_argument("--output", type=Path, required=True); p.set_defaults(handler=preflight)
    o = sub.add_parser("observer"); o.add_argument("--launch-plan", type=Path, required=True); o.add_argument("--session-root", type=Path, required=True); o.add_argument("--token-path", type=Path, required=True); o.add_argument("--session-date", required=True); o.add_argument("--status", type=Path, required=True); o.add_argument("--max-runtime-sec", type=float); o.set_defaults(handler=observer)
    s = sub.add_parser("status"); s.add_argument("--status", type=Path, required=True); s.add_argument("--release", default=""); s.set_defaults(handler=status)
    return int(args_handler(parser.parse_args()))


def args_handler(args: argparse.Namespace) -> int:
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
