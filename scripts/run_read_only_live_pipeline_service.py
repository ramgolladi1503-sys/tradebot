#!/usr/bin/env python3
"""LaunchAgent adapter for one canonical, current-session read-only run."""

from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    session_date = date.today().isoformat()
    preflight_root = Path(os.environ.get("TRADEBOT_PREFLIGHT_ROOT", ""))
    runtime_root = Path(os.environ.get("TRADEBOT_RUNTIME_ROOT", ""))
    token_path = Path(os.environ.get("TRADEBOT_TOKEN_PATH", "/Users/madhuram/.tradebot/credentials/kite_access_token"))
    source_sha = str(os.environ.get("TRADEBOT_COMMIT_SHA") or "").strip()
    if not preflight_root or not runtime_root or len(source_sha) != 40:
        raise RuntimeError("CANONICAL_SERVICE_CONFIGURATION_MISSING")
    authority_path = preflight_root / "subscription_tokens.json"
    payload = json.loads(authority_path.read_text(encoding="utf-8"))
    if payload.get("session_date") != session_date or payload.get("source_sha") != source_sha:
        raise RuntimeError("CURRENT_SUBSCRIPTION_AUTHORITY_MISMATCH")
    tokens = sorted({int(value) for value in payload.get("subscription_tokens") or () if int(value) > 0})
    if not tokens:
        raise RuntimeError("CURRENT_SUBSCRIPTION_TOKENS_MISSING")
    from core.read_only_live_pipeline import run_pipeline
    return run_pipeline(
        session_date=session_date, runtime_root=runtime_root, token_path=token_path,
        subscription_tokens=tokens,
    )


if __name__ == "__main__":
    raise SystemExit(main())

