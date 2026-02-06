from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json
from pathlib import Path
import sys

from core.trade_store import insert_trade, insert_outcome

LOG_PATH = Path("data/trade_log.json")
UPD_PATH = Path("data/trade_updates.json")

def load_updates():
    updates = {}
    if not UPD_PATH.exists():
        return updates
    with UPD_PATH.open() as f:
        for line in f:
            if not line.strip():
                continue
            try:
                u = json.loads(line)
            except Exception:
                continue
            tid = u.get("trade_id")
            if tid:
                updates[tid] = u
    return updates

if __name__ == "__main__":
    if not LOG_PATH.exists():
        raise SystemExit("trade_log.json not found")
    updates = load_updates()
    inserted = 0
    outcomes = 0
    with LOG_PATH.open() as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            # merge last update if exists
            tid = entry.get("trade_id")
            if tid and tid in updates:
                entry.update(updates[tid])
            insert_trade(entry)
            inserted += 1
            if entry.get("exit_price") is not None:
                insert_outcome(entry)
                outcomes += 1
    print(f"Backfilled trades: {inserted}, outcomes: {outcomes}")
