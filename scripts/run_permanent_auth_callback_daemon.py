#!/usr/bin/env python3
"""Standalone permanent OAuth callback daemon for TradeBot Kite login.

Listens on localhost:8765 for Kite OAuth redirects, provides a /health endpoint,
exchanges the request token for an access token atomically, and persists it.
Can be run continuously in the background or supervised via launchd/systemd.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.governed_morning_orchestrator import GovernedAuthCallbackServer


def main() -> int:
    parser = argparse.ArgumentParser(description="Permanent Kite OAuth callback daemon")
    parser.add_argument("--host", default="127.0.0.1", help="Callback host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Callback port (default: 8765)")
    parser.add_argument(
        "--token-path",
        type=Path,
        default=ROOT / ".runtime" / "kite_access_token",
        help="Access token destination path",
    )
    args = parser.parse_args()

    token_path = args.token_path.resolve()
    server = GovernedAuthCallbackServer(
        token_path=token_path,
        repo_root=ROOT,
        host=args.host,
        port=args.port,
    )

    started = server.start()
    if not started:
        print(f"[FATAL] Could not bind callback daemon to http://{args.host}:{args.port}/: {server.error}", file=sys.stderr)
        return 1

    print(f"[PERMANENT_AUTH_CALLBACK] Active on http://{args.host}:{args.port}/ (health: http://{args.host}:{args.port}/health)", flush=True)
    print(f"[PERMANENT_AUTH_CALLBACK] Writing valid tokens to: {token_path}", flush=True)

    running = True

    def handle_signal(sig, frame):
        nonlocal running
        print(f"\n[PERMANENT_AUTH_CALLBACK] Stopping on signal {sig}...", flush=True)
        running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        while running:
            time.sleep(1.0)
    finally:
        server.stop()
        print("[PERMANENT_AUTH_CALLBACK] Stopped cleanly.", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
