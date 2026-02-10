from pathlib import Path
import runpy
import sqlite3
import sys

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.trade_store import init_db


def main():
    db_path = Path(getattr(cfg, "TRADE_DB_PATH", "data/trades.db"))
    if not db_path.exists():
        init_db()
    if not db_path.exists():
        print("verify_trade_identity: FAIL missing trades DB. Generate trades via paper/live run.")
        return 2
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.execute("PRAGMA table_info(trades)")
    cols = {row[1] for row in cur.fetchall()}
    required = {"trade_id", "symbol", "instrument_type", "expiry", "strike", "right", "instrument_id"}
    missing_cols = sorted(required - cols)
    if missing_cols:
        con.close()
        print(f"verify_trade_identity: FAIL missing required columns in trades table: {', '.join(missing_cols)}")
        print("NEXT ACTION: run migrations (trade_store.init_db) and regenerate recent trades in current desk DB.")
        return 2
    cur.execute(
        """
        SELECT trade_id, symbol, instrument_type, expiry, strike, right, instrument_id
        FROM trades
        WHERE instrument_type IN ('OPT','FUT')
          AND (instrument_id IS NULL OR instrument_id = '' OR expiry IS NULL OR (instrument_type='OPT' AND (strike IS NULL OR right IS NULL)))
        LIMIT 5
        """
    )
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(1) FROM trades")
    total = int(cur.fetchone()[0] or 0)
    con.close()
    if total == 0:
        print("verify_trade_identity: FAIL no trade rows.")
        print("NEXT ACTION: run paper/live cycle to generate trade rows with contract identity.")
        return 2
    if rows:
        print(f"verify_trade_identity: FAIL missing identity fields (sample of {len(rows)} rows, total={total})")
        for row in rows:
            print(row)
        return 1
    print(f"verify_trade_identity: OK total_rows={total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
