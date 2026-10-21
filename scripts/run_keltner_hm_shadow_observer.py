#!/usr/bin/env python3
from __future__ import annotations
import argparse
import csv
from datetime import datetime
from core.keltner_hm_shadow.aggregation import Bar
from core.keltner_hm_shadow.observer import ShadowObserver

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars-csv", required=True)
    parser.add_argument("--contract", default="core/keltner_hm_shadow/contract.json")
    parser.add_argument("--events", required=True)
    parser.add_argument("--state", required=True)
    args = parser.parse_args()
    observer = ShadowObserver(args.contract, args.events, args.state)
    with open(args.bars_csv, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            observer.ingest(Bar(symbol=row["symbol"], start=datetime.fromisoformat(row["start"]),
                completion=datetime.fromisoformat(row["completion"]), open=float(row["open"]),
                high=float(row["high"]), low=float(row["low"]), close=float(row["close"]),
                session_id=row["session_id"], source=row.get("source", "fixture"),
                sequence=int(row["sequence"]) if row.get("sequence") else None))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
