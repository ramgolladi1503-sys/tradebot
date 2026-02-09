import sys
import time
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg
from core.trade_store import insert_trade, update_trade_fill_db

trade_id = f"TEST_FILL_{int(time.time())}"
insert_trade({
    "trade_id": trade_id,
    "timestamp": str(time.time()),
    "symbol": "NIFTY",
    "instrument": "OPT",
    "instrument_token": 0,
    "side": "BUY",
    "entry": 100.0,
    "stop_loss": 90.0,
    "target": 120.0,
    "qty": 1,
    "confidence": 0.5,
    "strategy": "TEST",
    "regime": "NEUTRAL",
})

update_trade_fill_db(trade_id, fill_price=123.45, latency_ms=5.0, slippage=0.1)

con = sqlite3.connect(cfg.TRADE_DB_PATH)
cur = con.execute("SELECT fill_price, latency_ms, slippage FROM trades WHERE trade_id=?", (trade_id,))
row = cur.fetchone()
con.close()

assert row is not None, "trade not found"
fill_price, latency_ms, slippage = row
assert abs(fill_price - 123.45) < 1e-6, f"fill_price mismatch: {fill_price}"
assert abs(latency_ms - 5.0) < 1e-6, f"latency mismatch: {latency_ms}"
assert abs(slippage - 0.1) < 1e-6, f"slippage mismatch: {slippage}"

print("verify_trade_fill_db: OK")
