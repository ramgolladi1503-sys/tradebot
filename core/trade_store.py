import sqlite3
from config import config as cfg
from pathlib import Path

def _conn():
    Path(cfg.TRADE_DB_PATH).parent.mkdir(exist_ok=True)
    return sqlite3.connect(cfg.TRADE_DB_PATH)

def init_db():
    with _conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            trade_id TEXT PRIMARY KEY,
            timestamp TEXT,
            symbol TEXT,
            instrument TEXT,
            instrument_token INTEGER,
            side TEXT,
            entry REAL,
            stop_loss REAL,
            target REAL,
            qty INTEGER,
            confidence REAL,
            strategy TEXT,
            regime TEXT,
            fill_price REAL,
            latency_ms REAL,
            slippage REAL,
            micro_pred REAL,
            execution_quality REAL
        )
        """)
        try:
            conn.execute("ALTER TABLE trades ADD COLUMN execution_quality REAL")
        except Exception:
            pass
        conn.execute("""
        CREATE TABLE IF NOT EXISTS outcomes (
            trade_id TEXT,
            exit_price REAL,
            exit_time TEXT,
            actual INTEGER,
            r_multiple REAL,
            r_label INTEGER
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_stats (
            timestamp TEXT,
            instrument TEXT,
            slippage_bps REAL,
            latency_ms REAL,
            fill_ratio REAL
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS depth_snapshots (
            timestamp TEXT,
            instrument_token INTEGER,
            depth_json TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS broker_fills (
            order_id TEXT,
            trade_id TEXT,
            symbol TEXT,
            side TEXT,
            qty INTEGER,
            price REAL,
            timestamp TEXT,
            exchange TEXT,
            instrument_token INTEGER
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            date TEXT PRIMARY KEY,
            trades INTEGER,
            pnl REAL,
            win_rate REAL,
            profit_factor REAL,
            sharpe REAL,
            max_drawdown REAL
        )
        """)

def insert_trade(entry):
    init_db()
    with _conn() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO trades
        (trade_id, timestamp, symbol, instrument, instrument_token, side, entry, stop_loss, target, qty,
         confidence, strategy, regime, fill_price, latency_ms, slippage, micro_pred, execution_quality)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            entry.get("trade_id"), entry.get("timestamp"), entry.get("symbol"), entry.get("instrument"),
            entry.get("instrument_token"), entry.get("side"), entry.get("entry"), entry.get("stop_loss"),
            entry.get("target"), entry.get("qty"), entry.get("confidence"), entry.get("strategy"),
            entry.get("regime"), entry.get("fill_price"), entry.get("latency_ms"), entry.get("slippage"),
            entry.get("micro_pred"), entry.get("execution_quality_score") or entry.get("execution_quality")
        ))

def insert_outcome(outcome):
    init_db()
    with _conn() as conn:
        conn.execute("""
        INSERT INTO outcomes (trade_id, exit_price, exit_time, actual, r_multiple, r_label)
        VALUES (?,?,?,?,?,?)
        """, (
            outcome.get("trade_id"), outcome.get("exit_price"), outcome.get("exit_time"),
            outcome.get("actual"), outcome.get("r_multiple"), outcome.get("r_label")
        ))

def fetch_recent_trades(limit=200):
    init_db()
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return cols, rows

def update_trade_fill_db(trade_id, fill_price, latency_ms=None, slippage=None):
    init_db()
    with _conn() as conn:
        conn.execute(
            "UPDATE trades SET fill_price = ?, latency_ms = ?, slippage = ? WHERE trade_id = ?",
            (fill_price, latency_ms, slippage, trade_id),
        )

def fetch_recent_outcomes(limit=200):
    init_db()
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM outcomes ORDER BY exit_time DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return cols, rows

def fetch_pnl_series(limit=1000):
    init_db()
    with _conn() as conn:
        cur = conn.execute("""
        SELECT t.timestamp, t.entry, o.exit_price, t.side, t.qty
        FROM trades t LEFT JOIN outcomes o ON t.trade_id = o.trade_id
        ORDER BY t.timestamp DESC LIMIT ?
        """, (limit,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return cols, rows

def insert_execution_stat(row):
    init_db()
    with _conn() as conn:
        conn.execute("""
        INSERT INTO execution_stats (timestamp, instrument, slippage_bps, latency_ms, fill_ratio)
        VALUES (?,?,?,?,?)
        """, (
            row.get("timestamp"), row.get("instrument"), row.get("slippage_bps"),
            row.get("latency_ms"), row.get("fill_ratio")
        ))

def fetch_execution_stats(limit=200):
    init_db()
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM execution_stats ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return cols, rows

def fetch_depth_snapshots(limit=200):
    init_db()
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM depth_snapshots ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return cols, rows

def fetch_depth_imbalance(limit=1000):
    init_db()
    with _conn() as conn:
        cur = conn.execute("SELECT timestamp, instrument_token, depth_json FROM depth_snapshots ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    return cols, rows

def insert_depth_snapshot(ts, instrument_token, depth_json):
    init_db()
    with _conn() as conn:
        conn.execute("""
        INSERT INTO depth_snapshots (timestamp, instrument_token, depth_json)
        VALUES (?,?,?)
        """, (ts, instrument_token, depth_json))
        limit = getattr(__import__("config.config", fromlist=["DEPTH_SNAPSHOT_LIMIT"]), "DEPTH_SNAPSHOT_LIMIT", 10000)
        conn.execute("""
        DELETE FROM depth_snapshots
        WHERE rowid NOT IN (
            SELECT rowid FROM depth_snapshots ORDER BY timestamp DESC LIMIT ?
        )
        """, (limit,))

def insert_broker_fill(row):
    init_db()
    with _conn() as conn:
        conn.execute("""
        INSERT INTO broker_fills
        (order_id, trade_id, symbol, side, qty, price, timestamp, exchange, instrument_token)
        VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            row.get("order_id"), row.get("trade_id"), row.get("symbol"),
            row.get("side"), row.get("qty"), row.get("price"),
            row.get("timestamp"), row.get("exchange"), row.get("instrument_token")
        ))

def insert_daily_stats(row):
    init_db()
    with _conn() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO daily_stats
        (date, trades, pnl, win_rate, profit_factor, sharpe, max_drawdown)
        VALUES (?,?,?,?,?,?,?)
        """, (
            row.get("date"), row.get("trades"), row.get("pnl"), row.get("win_rate"),
            row.get("profit_factor"), row.get("sharpe"), row.get("max_drawdown")
        ))
