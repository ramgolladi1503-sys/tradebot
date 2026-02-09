import sqlite3
import sys
from pathlib import Path

from config import config as cfg


def main():
    db_path = Path(getattr(cfg, "TRADE_DB_PATH", "data/trades.db"))
    if not db_path.exists():
        print("verify_trade_identity: FAIL missing trades DB")
        return 2
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
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
    con.close()
    if rows:
        print("verify_trade_identity: FAIL missing identity fields")
        for row in rows:
            print(row)
        return 1
    print("verify_trade_identity: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
