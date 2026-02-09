#!/usr/bin/env python
import argparse
import json
import sqlite3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg

def _check_sqlite(db_path: Path, min_non_null: int) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("PRAGMA table_info(decision_events)")
        cols = [r[1] for r in cur.fetchall()]
        if "quote_age_sec" not in cols:
            print("quote_age_sec column missing in sqlite")
            return False
        total = conn.execute("SELECT COUNT(*) FROM decision_events").fetchone()[0]
        nonnull = conn.execute("SELECT COUNT(*) FROM decision_events WHERE quote_age_sec IS NOT NULL").fetchone()[0]
        print(f"decision_events.sqlite total={total} quote_age_sec_nonnull={nonnull}")
        if total == 0:
            print("FAIL: no decision events in sqlite")
            return False
        if nonnull < min_non_null:
            print("FAIL: insufficient non-null quote_age_sec in sqlite")
            return False
        return True
    finally:
        conn.close()

def _check_jsonl(jsonl_path: Path, min_non_null: int) -> bool:
    total = 0
    nonnull = 0
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            total += 1
            if row.get("quote_age_sec") is not None:
                nonnull += 1
    print(f"decision_events.jsonl total={total} quote_age_sec_nonnull={nonnull}")
    if total == 0:
        print("FAIL: no decision events in jsonl")
        return False
    if nonnull < min_non_null:
        print("FAIL: insufficient non-null quote_age_sec in jsonl")
        return False
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-non-null", type=int, default=1)
    args = ap.parse_args()

    db_path = Path(getattr(cfg, "DECISION_SQLITE_PATH", "logs/decision_events.sqlite"))
    jsonl_path = Path(getattr(cfg, "DECISION_LOG_PATH", "logs/decision_events.jsonl"))

    if db_path.exists():
        ok = _check_sqlite(db_path, args.min_non_null)
    elif jsonl_path.exists():
        ok = _check_jsonl(jsonl_path, args.min_non_null)
    else:
        print("FAIL: no decision_events sqlite or jsonl found")
        ok = False

    if not ok:
        sys.exit(1)
    print("OK: quote_age_sec present in DecisionEvents")

if __name__ == "__main__":
    main()
