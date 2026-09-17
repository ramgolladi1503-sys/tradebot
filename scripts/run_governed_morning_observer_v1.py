#!/usr/bin/env python3
"""Governed morning observer launcher entry point with automatic auth continuation."""
from __future__ import annotations

import argparse
import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.governed_morning_orchestrator import GovernedMorningOrchestrator, LauncherState


def main() -> int:
    parser = argparse.ArgumentParser(description="Governed morning observer launcher")
    parser.add_argument("--session-date", help="Session date in YYYY-MM-DD")
    parser.add_argument("--repo", type=Path, default=ROOT, help="Repository root path")
    parser.add_argument("--state-root", type=Path, default=Path("/Volumes/TradeBotData"), help="State root volume path")
    parser.add_argument("--token-path", type=Path, help="Explicit access token path")
    parser.add_argument("--auth-timeout-seconds", type=float, default=600.0, help="Timeout in seconds to wait for human login")
    parser.add_argument("--expected-sha", help="Expected certified release commit SHA")
    parser.add_argument("--release-store", type=Path, help="Explicit ReleaseStore directory path")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open browser on login required")
    parser.add_argument("--dry-run", action="store_true", help="Perform pre-session checks and arming without spawning observer process")
    args = parser.parse_args()

    orchestrator = GovernedMorningOrchestrator(
        repo_root=args.repo,
        state_root=args.state_root,
        session_date=args.session_date,
        token_path=args.token_path,
        auth_timeout_seconds=args.auth_timeout_seconds,
        expected_release_sha=args.expected_sha,
        storage_volume=args.state_root,
        release_store_path=args.release_store,
        open_browser=not args.no_browser,
        dry_run=args.dry_run,
    )

    def handle_signal(sig, frame):
        orchestrator.stop(f"signal_{sig}")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    final_state = orchestrator.run()

    if final_state in {LauncherState.OBSERVER_RUNNING, LauncherState.STOPPED}:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
