#!/usr/bin/env python3
"""Single command surface for governed Morning Readiness operations."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Direct script execution places ``scripts/`` ahead of the repository root.
# Bind imports to this checkout so the governed launcher has the same behavior
# as module/test execution.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.morning_session_root import SessionRootError, create_session_root
from core.morning_operator_status import build_status
from core.certified_release_store import ReleaseStore, ReleaseStoreError

SAFE_GIT_CONFIG = [
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "filter.lfs.process=",
    "-c",
    "filter.lfs.clean=",
    "-c",
    "filter.lfs.smudge=",
    "-c",
    "filter.lfs.required=false",
]


def git_output(*args: str, timeout: float = 15.0) -> str:
    return subprocess.check_output(["git", *SAFE_GIT_CONFIG, *args], text=True, timeout=timeout).strip()


def tracked_tree_clean() -> bool:
    common = ["git", *SAFE_GIT_CONFIG]
    unstaged = subprocess.run([*common, "diff", "--quiet"], timeout=20.0)
    staged = subprocess.run([*common, "diff", "--cached", "--quiet"], timeout=20.0)
    return unstaged.returncode == 0 and staged.returncode == 0


def resolve_release(args: argparse.Namespace) -> str:
    explicit = getattr(args, "release", None)
    store_root = getattr(args, "release_store_root", None)
    if explicit and store_root:
        raise SessionRootError("release_and_release_store_are_mutually_exclusive")
    if explicit:
        return explicit
    if not store_root:
        raise SessionRootError("release_authority_missing")
    try:
        current = ReleaseStore(store_root).read()
    except ReleaseStoreError as exc:
        raise SessionRootError("release_store_invalid") from exc
    if current is None:
        raise SessionRootError("release_store_uninitialized")
    return current["certified_live_sha"]


def preflight(args: argparse.Namespace) -> int:
    result = {"release_sha_actual": "", "release_sha_match": False, "worktree_clean": False, "preflight_pass": False}
    try:
        release = resolve_release(args)
        actual = git_output("rev-parse", "HEAD")
        clean = tracked_tree_clean()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        result["blocker"] = "git_authority_check_failed"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2
    except SessionRootError as exc:
        result["blocker"] = str(exc)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2
    result.update({"release_sha_actual": actual, "worktree_clean": clean})
    try:
        result["release_sha_expected"] = release
        result["release_sha_match"] = actual == release
        if actual != release or not clean:
            raise SessionRootError("release_authority_or_clean_tree_failed")
        result["session_root"] = create_session_root(external_root=args.external_root, session_date=args.session_date, release_sha=release)
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
    supervisor = [sys.executable, "scripts/morning_observer_supervisor.py", "--status", str(args.status), "--session-root", str(args.session_root), "--", *command]
    return subprocess.call(supervisor)


def status(args: argparse.Namespace) -> int:
    payload = json.loads(args.status.read_text(encoding="utf-8")) if args.status.exists() else build_status(state="FAIL_CLOSED", release_sha=args.release, blockers=["status_missing"])
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def live(args: argparse.Namespace) -> int:
    """Run the repository's existing read-only market-data orchestrator."""
    try:
        actual = git_output("rev-parse", "HEAD")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print(json.dumps({"state": "FAIL_CLOSED", "blocker": "git_authority_check_failed"}))
        return 2
    try:
        release = resolve_release(args)
    except SessionRootError as exc:
        print(json.dumps({"state": "FAIL_CLOSED", "blocker": str(exc)}))
        return 2
    if actual != release:
        print(json.dumps({"state": "FAIL_CLOSED", "blocker": "release_sha_mismatch"}))
        return 2
    env = dict(__import__("os").environ)
    env.update({"TRADING_BOT_TOKEN_PATH": str(args.token_path.resolve()), "TRADEBOT_READ_ONLY": "true", "ALLOW_LIVE_ORDERS": "0", "AUTO_ORDER": "0", "AUTO_TRADE": "0", "PAPER_TRADING_ENABLED": "false"})
    command = [sys.executable, "scripts/run_market_event_graph_live_session_v1.py", "--session-date", args.session_date, "--output-root", str(args.output_root), "--authority-artifact", str(args.authority_artifact)]
    if args.kite_instruments_file:
        command.extend(["--kite-instruments-file", str(args.kite_instruments_file)])
    if args.preflight_only:
        command.append("--preflight-only")
    return subprocess.call(command, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(prog="tradebot-morning-readiness")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("preflight"); p.add_argument("--release"); p.add_argument("--release-store-root", type=Path); p.add_argument("--session-date", required=True); p.add_argument("--external-root", type=Path, required=True); p.add_argument("--output", type=Path, required=True); p.set_defaults(handler=preflight)
    o = sub.add_parser("observer"); o.add_argument("--launch-plan", type=Path, required=True); o.add_argument("--session-root", type=Path, required=True); o.add_argument("--token-path", type=Path, required=True); o.add_argument("--session-date", required=True); o.add_argument("--status", type=Path, required=True); o.add_argument("--max-runtime-sec", type=float); o.set_defaults(handler=observer)
    s = sub.add_parser("status"); s.add_argument("--status", type=Path, required=True); s.add_argument("--release", default=""); s.set_defaults(handler=status)
    l = sub.add_parser("live", help="run the existing governed read-only market-data orchestrator"); l.add_argument("--release"); l.add_argument("--release-store-root", type=Path); l.add_argument("--session-date", required=True); l.add_argument("--output-root", type=Path, required=True); l.add_argument("--token-path", type=Path, required=True); l.add_argument("--authority-artifact", type=Path, required=True); l.add_argument("--kite-instruments-file", type=Path); l.add_argument("--preflight-only", action="store_true"); l.set_defaults(handler=live)
    return int(args_handler(parser.parse_args()))


def args_handler(args: argparse.Namespace) -> int:
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
