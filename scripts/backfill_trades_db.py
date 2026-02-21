# Migration note:
# Backfill now ensures canonical trade-log creation and skips gracefully when missing/unreadable.

from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json

from core.trade_store import insert_trade, insert_outcome
from core.trade_log_paths import ensure_trade_log_exists

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

def main() -> dict:
    log_path = ensure_trade_log_exists()
    updates = load_updates()
    inserted = 0
    outcomes = 0
    skipped_reasons: list[str] = []
    try:
        with log_path.open("r", encoding="utf-8") as f:
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
    except Exception as exc:
        print(f"[backfill_trades_db][WARN] cannot read trade log at {log_path}: {exc}")
        skipped_reasons.append(f"trade_log_unreadable:{exc}")
    print(f"Backfilled trades: {inserted}, outcomes: {outcomes}")
    status = "skipped" if skipped_reasons else "ok"
    return {
        "status": status,
        "reasons": skipped_reasons,
        "inserted": inserted,
        "outcomes": outcomes,
        "path": str(log_path),
    }


if __name__ == "__main__":
    main()
