#!/usr/bin/env python3
"""Bounded metadata-only Kite preflight for the canonical read-only pipeline."""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    from core.auth import get_kite_client

    client = get_kite_client(repo_root_path=REPO_ROOT)
    client.profile()
    client.margins()
    print("PROFILE_CALL=PASS")
    print("MARGINS_CALL=PASS")
    for exchange in ("NSE", "NFO", "BFO"):
        rows = client.instruments(exchange)
        symbols = {
            str(row.get("name") or row.get("tradingsymbol") or "").upper()
            for row in rows if isinstance(row, dict)
        }
        print(f"{exchange}_ROWS={len(rows)}")
        print(f"{exchange}_NIFTY_PRESENT={'NIFTY' in symbols}")
        print(f"{exchange}_BANKNIFTY_PRESENT={'BANKNIFTY' in symbols}")
    print("BROKER_WRITE_AUTHORITY=false")
    print("ORDER_AUTHORITY=false")
    print("BROKER_ORDER_CALLS=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

