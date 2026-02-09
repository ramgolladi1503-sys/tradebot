from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from config import config as cfg


def _load_sqlite(path: str) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(path) as conn:
            return pd.read_sql_query("SELECT * FROM decision_events", conn)
    except Exception:
        return pd.DataFrame()


def _load_jsonl(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    rows = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return pd.DataFrame(rows)


def main():
    df = _load_sqlite(getattr(cfg, "TRADE_DB_PATH", "data/trades.db"))
    if df.empty:
        df = _load_jsonl(getattr(cfg, "DECISION_LOG_PATH", "logs/decision_events.jsonl"))
    if df.empty:
        print("No decision events found")
        return
    Path("data").mkdir(exist_ok=True)
    out_parquet = Path("data/decision_dataset.parquet")
    out_csv = Path("data/decision_dataset.csv")
    df.to_parquet(out_parquet, index=False)
    df.to_csv(out_csv, index=False)
    print(f"Saved {len(df)} decision rows to {out_parquet} and {out_csv}")


if __name__ == "__main__":
    main()
