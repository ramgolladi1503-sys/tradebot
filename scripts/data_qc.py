from pathlib import Path
import runpy
from core.paths import logs_dir

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import json
import sqlite3
import pandas as pd

from config import config as cfg

OUT = logs_dir() / "data_qc.json"


def _qc_table(conn, table, ts_col="timestamp"):
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    except Exception:
        return {"table": table, "rows": 0, "error": "missing"}
    if df.empty:
        return {"table": table, "rows": 0}
    res = {"table": table, "rows": int(len(df))}
    if ts_col in df.columns:
        df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
        res["null_ts"] = int(df[ts_col].isna().sum())
        res["min_ts"] = str(df[ts_col].min())
        res["max_ts"] = str(df[ts_col].max())
    if table in ("ticks", "trades"):
        null_rate = float(df[ts_col].isna().mean()) if ts_col in df.columns else 0.0
    else:
        null_rate = float(df.isna().mean().max())
    res["max_null_rate"] = null_rate
    res["null_rate_ok"] = null_rate <= getattr(cfg, "QC_MAX_NULL_RATE", 0.1)
    return res


def _ensure_trade_db_ready(db_path: Path) -> dict:
    """
    Root-cause fix:
    Daily ops can run before any trade rows are inserted. In that case the DB file
    may not exist yet, even though schema init is safe and deterministic.
    """
    if db_path.exists():
        return {"created": False, "path": str(db_path)}
    try:
        from core.trade_store import init_db

        init_db()
    except Exception as exc:
        raise RuntimeError(f"cannot initialize trade db at {db_path}: {exc}") from exc
    return {"created": bool(db_path.exists()), "path": str(db_path)}


def run_qc() -> dict:
    db = Path(cfg.TRADE_DB_PATH)
    db_state = _ensure_trade_db_ready(db)
    conn = sqlite3.connect(str(db))
    try:
        qc_rows = [
            _qc_table(conn, "ticks"),
            _qc_table(conn, "depth_snapshots"),
            _qc_table(conn, "trades"),
            _qc_table(conn, "broker_fills"),
        ]
    finally:
        conn.close()

    payload = {
        "status": "ok",
        "db_path": str(db),
        "db_created": bool(db_state.get("created")),
        "tables": qc_rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(payload)
    return payload


if __name__ == "__main__":
    try:
        run_qc()
    except Exception as exc:
        raise SystemExit(str(exc))
