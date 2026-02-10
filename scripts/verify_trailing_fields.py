from pathlib import Path
import runpy
import sqlite3
import sys

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.trade_store import init_db


def main() -> int:
    init_db()
    db_path = Path(getattr(cfg, "TRADE_DB_PATH", "data/desks/DEFAULT/trades.db"))
    if not db_path.exists():
        print("verify_trailing_fields: FAIL missing trades DB.")
        print("NEXT ACTION: run paper/live cycle to generate trades.")
        return 2
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.execute("PRAGMA table_info(trades)")
    cols = {row[1] for row in cur.fetchall()}
    required = {"trailing_enabled", "trail_stop_init", "trail_stop_last", "trail_updates"}
    missing = sorted(required - cols)
    if missing:
        con.close()
        print(f"verify_trailing_fields: FAIL missing columns: {', '.join(missing)}")
        print("NEXT ACTION: run trade_store.init_db() migration path.")
        return 2
    cur.execute("SELECT COUNT(1) FROM trades WHERE trailing_enabled=1")
    total = int(cur.fetchone()[0] or 0)
    if total == 0:
        con.close()
        print("verify_trailing_fields: FAIL no trailing-enabled trades found.")
        print("NEXT ACTION: run paper session with open trades to produce trailing records.")
        return 2
    cur.execute(
        """
        SELECT trade_id, trail_stop_init, trail_stop_last, trail_updates
        FROM trades
        WHERE trailing_enabled=1
          AND (trail_stop_init IS NULL OR trail_stop_last IS NULL OR trail_updates IS NULL)
        LIMIT 5
        """
    )
    bad = cur.fetchall()
    con.close()
    if bad:
        print("verify_trailing_fields: FAIL invalid trailing fields.")
        for row in bad:
            print(row)
        return 1
    print(f"verify_trailing_fields: OK trailing_rows={total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
