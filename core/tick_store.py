import sqlite3
from pathlib import Path
from config import config as cfg

def _conn():
    Path(cfg.TRADE_DB_PATH).parent.mkdir(exist_ok=True)
    return sqlite3.connect(cfg.TRADE_DB_PATH)

def init_ticks():
    with _conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ticks (
            timestamp TEXT,
            instrument_token INTEGER,
            last_price REAL,
            volume INTEGER,
            oi INTEGER
        )
        """)

def insert_tick(ts, token, last_price, volume, oi):
    init_ticks()
    # normalize timestamp to ISO string
    if ts is None or ts == "" or ts == "None":
        from datetime import datetime
        ts = datetime.now().isoformat()
    if not isinstance(ts, str):
        try:
            # handle epoch seconds
            if isinstance(ts, (int, float)):
                from datetime import datetime
                ts = datetime.fromtimestamp(ts).isoformat()
            else:
                ts = str(ts)
        except Exception:
            from datetime import datetime
            ts = datetime.now().isoformat()
    if isinstance(ts, str) and ts.strip().lower() in ("nat", "nan", "none", ""):
        from datetime import datetime
        ts = datetime.now().isoformat()
    with _conn() as conn:
        conn.execute("""
        INSERT INTO ticks (timestamp, instrument_token, last_price, volume, oi)
        VALUES (?,?,?,?,?)
        """, (ts, token, last_price, volume, oi))
