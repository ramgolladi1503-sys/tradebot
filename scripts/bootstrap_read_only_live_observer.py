#!/usr/bin/env python3
"""Minimal current-session bootstrap for the dedicated read-only observer."""

from __future__ import annotations

import argparse
from datetime import date
import os
from pathlib import Path
import subprocess

from core.kite_read_only_observation_runtime import run_observation, safe_environment, safety_contract
from core.live_consumer_contract import CANONICAL_CONSUMERS, validate_consumer_registry, write_consumer_registry
from core.live_runtime_artifacts import write_pending_runtime_artifacts
from core.live_session_manifest import LiveSessionManifest, write_session_manifest
from core.read_only_instrument_authority import build_instrument_authority, fetch_current_instruments
from core.read_only_launch_plan import build_current_launch_plan, write_current_launch_plan


def _source_sha() -> str:
    value = str(os.environ.get("TRADEBOT_COMMIT_SHA") or "").strip()
    if value:
        return value
    raise RuntimeError("READ_ONLY_SOURCE_SHA_REQUIRED")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--token-path", required=True, type=Path)
    parser.add_argument("--subscription-token", action="append", type=int, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.session_date != date.today().isoformat():
        raise RuntimeError("READ_ONLY_SESSION_DATE_NOT_CURRENT")
    if not args.token_path.is_file() or (args.token_path.stat().st_mode & 0o077):
        raise RuntimeError("READ_ONLY_TOKEN_METADATA_INVALID")
    source_sha = _source_sha()
    env = safe_environment()
    safety_contract(env, child_command=["read-only-bootstrap"], child_pid=None)
    os.environ.update(env)
    from core.auth import get_kite_client
    client = get_kite_client(repo_root_path=Path(__file__).resolve().parents[1])
    client.profile()
    client.margins()
    session_id = str(os.environ.get("RUN_ID") or f"kite-read-only-{args.session_date}")
    args.runtime_root.mkdir(parents=True, exist_ok=True)
    validate_consumer_registry(CANONICAL_CONSUMERS)
    write_consumer_registry(args.runtime_root / "CONSUMERS.json", session_id=session_id, source_sha=source_sha)
    write_pending_runtime_artifacts(args.runtime_root, session_id=session_id, source_sha=source_sha)
    rows = fetch_current_instruments(client)
    authority = build_instrument_authority(rows=rows, session_date=args.session_date, source_sha=source_sha, output_root=args.runtime_root)
    plan = build_current_launch_plan(
        session_id=session_id, session_date=args.session_date, source_sha=source_sha,
        runtime_root=args.runtime_root, instrument_manifest=authority,
        subscription_tokens=args.subscription_token, consumer_registry_path=str(args.runtime_root / "CONSUMERS.json"),
    )
    write_current_launch_plan(args.runtime_root / "launch_plan.json", plan)
    manifest = LiveSessionManifest(
        session_date=args.session_date, session_id=session_id, source_sha=source_sha, observer_sha=source_sha,
        observer_pid=os.getpid(), runtime_root=str(args.runtime_root.resolve()),
        sqlite_path=plan["sqlite_path"], instrument_master_path=authority["raw_instrument_path"],
        instrument_master_sha=authority["raw_instrument_sha256"], auth_state="PASS", feed_state="PENDING",
        persistence_state="PENDING", subscription_count=plan["subscription_count"],
        consumer_registry=tuple(CANONICAL_CONSUMERS),
    )
    write_session_manifest(args.runtime_root / "SESSION_MANIFEST.json", manifest)
    if args.validate_only:
        return 0
    return run_observation(launch_plan=plan, output_root=args.runtime_root, token_path=args.token_path, session_date=args.session_date)


if __name__ == "__main__":
    raise SystemExit(main())
