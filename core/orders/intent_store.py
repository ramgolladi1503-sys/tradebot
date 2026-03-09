from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path

from config import config as cfg
from core.fs_utils import ensure_parent_dir
from core.orders.order_intent import OrderIntent
from core.paths import logs_dir


_LOCK = threading.RLock()


def _store_path() -> Path:
    configured = str(getattr(cfg, "ORDER_INTENT_STORE_PATH", "") or "").strip()
    if "ORDER_INTENT_STORE_PATH" not in os.environ:
        trade_db = Path(str(getattr(cfg, "TRADE_DB_PATH", "") or "")).expanduser()
        if str(trade_db).strip():
            return trade_db.with_name("order_intents.sqlite")
        return logs_dir() / "order_intents.sqlite"
    if not configured:
        return logs_dir() / "order_intents.sqlite"
    return Path(configured).expanduser()


def _connect() -> sqlite3.Connection:
    path = _store_path()
    ensure_parent_dir(path)
    conn = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS order_intents (
            client_order_id TEXT PRIMARY KEY,
            trade_id TEXT,
            intent_type TEXT,
            symbol TEXT,
            side TEXT,
            qty INTEGER,
            limit_price REAL,
            status TEXT,
            updated_at REAL
        )
        """
    )
    return conn


def get_intent(client_order_id: str) -> OrderIntent | None:
    key = str(client_order_id or "").strip()
    if not key:
        return None
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                """
                SELECT client_order_id, trade_id, intent_type, symbol, side, qty, limit_price, status
                FROM order_intents
                WHERE client_order_id=?
                """,
                (key,),
            ).fetchone()
        finally:
            conn.close()
    if row is None:
        return None
    return OrderIntent(
        trade_id=row["trade_id"],
        intent_type=row["intent_type"] or "PLACE_ORDER",
        symbol=row["symbol"] or "",
        side=row["side"] or "",
        qty=int(row["qty"] or 0),
        limit_price=row["limit_price"],
        client_order_id=row["client_order_id"],
        status=(row["status"] or "NEW").upper(),
        order_type="LIMIT",
        product="MIS",
        exchange="NFO",
        strategy_id="UNKNOWN",
        timestamp_bucket=0,
    )


def upsert_intent(intent: OrderIntent) -> OrderIntent:
    client_order_id = str(intent.client_order_id or "").strip()
    if not client_order_id:
        client_order_id = OrderIntent.compute_client_order_id(
            trade_id=intent.trade_id,
            intent_type=intent.intent_type,
            symbol=intent.symbol,
            side=intent.side,
        )
        intent = OrderIntent(
            **{**intent.__dict__, "client_order_id": client_order_id}
        )

    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO order_intents (
                    client_order_id, trade_id, intent_type, symbol, side, qty, limit_price, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_order_id) DO UPDATE SET
                    trade_id=excluded.trade_id,
                    intent_type=excluded.intent_type,
                    symbol=excluded.symbol,
                    side=excluded.side,
                    qty=excluded.qty,
                    limit_price=excluded.limit_price,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    client_order_id,
                    intent.trade_id,
                    str(intent.intent_type or "PLACE_ORDER").upper(),
                    str(intent.symbol or "").upper(),
                    str(intent.side or "").upper(),
                    int(intent.qty or 0),
                    None if intent.limit_price is None else float(intent.limit_price),
                    str(intent.status or "NEW").upper(),
                    float(time.time()),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    return intent
