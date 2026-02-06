from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import time
from datetime import datetime
from pathlib import Path
import sys

from core.kite_client import kite_client
from core.trade_store import insert_broker_fill

def sync_once():
    kite_client.ensure()
    if not kite_client.kite:
        print("Kite not initialized.")
        return 0
    try:
        trades = kite_client.trades()
    except Exception as e:
        print(f"Trade fetch failed: {e}")
        return 0

    count = 0
    for tr in trades:
        row = {
            "order_id": tr.get("order_id"),
            "trade_id": tr.get("trade_id"),
            "symbol": tr.get("tradingsymbol"),
            "side": tr.get("transaction_type"),
            "qty": tr.get("quantity"),
            "price": tr.get("average_price"),
            "timestamp": tr.get("exchange_timestamp") or tr.get("order_timestamp") or str(datetime.now()),
            "exchange": tr.get("exchange"),
            "instrument_token": tr.get("instrument_token"),
        }
        try:
            insert_broker_fill(row)
            count += 1
        except Exception:
            pass
    return count

if __name__ == "__main__":
    n = sync_once()
    print(f"Synced {n} broker fills")
