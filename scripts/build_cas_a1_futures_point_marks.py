from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aixion_trade_intelligence.cas_a1_tick_points import CasA1TickPointError, extract_frozen_futures_points
from aixion_trade_intelligence.storage import atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract frozen CAS-A1 futures 15:29/15:39 marks from persisted tick DB read-only")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--futures-token", type=int, required=True)
    parser.add_argument("--futures-instrument", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = extract_frozen_futures_points(
            db_path=args.db,
            futures_token=args.futures_token,
            futures_instrument=args.futures_instrument,
            session_date=args.session_date,
        )
    except CasA1TickPointError as exc:
        print(json.dumps({
            "status": "CAS_A1_FUTURES_POINT_MARKS_BLOCKED",
            "session_date": args.session_date,
            "reason": str(exc),
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
        }, sort_keys=True))
        return 2
    atomic_write_json(args.output, payload)
    print(json.dumps({
        "status": "CAS_A1_FUTURES_POINT_MARKS_READY",
        "session_date": args.session_date,
        "output": str(args.output),
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
