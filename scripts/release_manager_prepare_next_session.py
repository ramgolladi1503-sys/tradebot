#!/usr/bin/env python3
"""Prepare an offline next-session readiness artifact from the certified release pointer."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.certified_release_store import ReleaseStore, ReleaseStoreError


def _authority_ok(path: Path | None, session_date: str) -> tuple[bool, str]:
    if path is None:
        return False, "authority_artifact_missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "authority_artifact_unreadable"
    if payload.get("authority_verdict") != "PASS" or payload.get("independent_verifier_status") != "PASS":
        return False, "authority_artifact_not_pass"
    if payload.get("session_date") != session_date:
        return False, "authority_session_stale"
    return True, "PASS"


def prepare(state_root: Path, session_date: str, output: Path, authority_artifact: Path | None = None) -> dict:
    try:
        current = ReleaseStore(state_root).read()
    except ReleaseStoreError as exc:
        current = None
        blocker = "release_store_invalid:" + str(exc)
    else:
        blocker = ""
    authority_pass, authority_status = _authority_ok(authority_artifact, session_date)
    blockers = []
    if current is None:
        blockers.append(blocker or "release_store_uninitialized")
    if not authority_pass:
        blockers.append(authority_status)
    payload = {
        "schema_version": 1,
        "contract_id": "RELEASE_MANAGER_NEXT_SESSION_PREP_V1",
        "session_date": session_date,
        "prepared_at": datetime.now().astimezone().isoformat(),
        "certified_live_sha": (current or {}).get("certified_live_sha"),
        "fallback_live_sha": (current or {}).get("fallback_live_sha"),
        "release_event_sha256": (current or {}).get("event_sha256"),
        "authority_artifact": str(authority_artifact) if authority_artifact else None,
        "authority_status": authority_status,
        "next_session_status": "READY" if not blockers else "BLOCKED",
        "blockers": blockers,
        "read_only": True,
        "broker_api_called": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "orders_placed": 0,
        "orders_modified": 0,
        "orders_cancelled": 0,
    }
    if output.exists():
        raise FileExistsError("next_session_artifact_exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authority-artifact", type=Path)
    args = parser.parse_args()
    payload = prepare(args.state_root, args.session_date, args.output, authority_artifact=args.authority_artifact)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["next_session_status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
