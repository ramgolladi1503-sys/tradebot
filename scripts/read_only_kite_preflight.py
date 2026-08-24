#!/usr/bin/env python3
"""Bounded metadata-only Kite preflight for the canonical read-only pipeline."""

from __future__ import annotations

from pathlib import Path
import sys
import argparse
import json
from datetime import date

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path)
    args = parser.parse_args()
    from core.auth import get_kite_client
    from core.live_consumer_contract import CANONICAL_CONSUMERS
    from core.read_only_instrument_authority import build_instrument_authority
    from core.read_only_subscription_authority import build_subscription_authority

    client = get_kite_client(repo_root_path=REPO_ROOT)
    client.profile()
    client.margins()
    print("PROFILE_CALL=PASS")
    print("MARGINS_CALL=PASS")
    all_rows = []
    for exchange in ("NSE", "NFO", "BFO"):
        rows = client.instruments(exchange)
        all_rows.extend(row for row in rows if isinstance(row, dict))
        symbols = {
            str(row.get("name") or row.get("tradingsymbol") or "").upper()
            for row in rows if isinstance(row, dict)
        }
        print(f"{exchange}_ROWS={len(rows)}")
        print(f"{exchange}_NIFTY_PRESENT={'NIFTY' in symbols}")
        print(f"{exchange}_BANKNIFTY_PRESENT={'BANKNIFTY' in symbols}")
    if args.runtime_root is not None:
        args.runtime_root.mkdir(parents=True, exist_ok=True)
        authority = build_instrument_authority(
            rows=all_rows, session_date=date.today().isoformat(),
            source_sha=str(__import__("os").environ.get("TRADEBOT_COMMIT_SHA") or ""),
            output_root=args.runtime_root,
        )
        build_subscription_authority(
            rows=all_rows, session_id=str(__import__("os").environ.get("RUN_ID") or f"kite-read-only-{date.today().isoformat()}"),
            session_date=date.today().isoformat(),
            source_sha=str(__import__("os").environ.get("TRADEBOT_COMMIT_SHA") or ""),
            instrument_authority=authority, consumer_registry=CANONICAL_CONSUMERS,
            output_path=args.runtime_root / "subscription_tokens.json",
        )
    print("BROKER_WRITE_AUTHORITY=false")
    print("ORDER_AUTHORITY=false")
    print("BROKER_ORDER_CALLS=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
