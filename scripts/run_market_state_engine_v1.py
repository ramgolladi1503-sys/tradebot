#!/usr/bin/env python3
"""Run MARKET_STATE_ENGINE_V1 against a canonical market snapshot file.

Read-only sidecar: no broker import, no order/candidate API, no execution authority.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from core.live_market_state_runtime import ARTIFACT_NAME, previous_zones_from_payload, publish_from_market_snapshot


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(value, dict) and isinstance(value.get("payload"), dict):
        return dict(value["payload"])
    return value if isinstance(value, dict) else {}


def run_once(*, market_snapshot_path: Path, output_root: Path, session_id: str, source_sha: str) -> dict:
    previous = _read_json(output_root / ARTIFACT_NAME)
    return publish_from_market_snapshot(
        output_root,
        market_snapshot=_read_json(market_snapshot_path),
        session_id=session_id,
        source_sha=source_sha,
        previous_zones=previous_zones_from_payload(previous),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-snapshot", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--cadence-sec", type=float, default=1.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.cadence_sec < 0.25:
        raise SystemExit("cadence must be >= 0.25 sec")
    while True:
        payload = run_once(
            market_snapshot_path=args.market_snapshot,
            output_root=args.output_root,
            session_id=args.session_id,
            source_sha=args.source_sha,
        )
        print(json.dumps({
            "verdict": payload["verdict"],
            "zones": {k: v["zone"] for k, v in payload["indices"].items()},
            "cross_index": payload["cross_index"],
        }, sort_keys=True), flush=True)
        if args.once:
            return 0
        time.sleep(args.cadence_sec)


if __name__ == "__main__":
    raise SystemExit(main())
