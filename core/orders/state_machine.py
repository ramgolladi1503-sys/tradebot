"""Migration note:
Strict order lifecycle state machine with SQLite-backed durable persistence.
All transitions are validated, transactional, and thread-safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable

from config import config as cfg


class OrderState(str, Enum):
    NEW = "NEW"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class OrderStateTransitionError(RuntimeError):
    def __init__(self, current_state: OrderState, next_state: OrderState):
        self.current_state = current_state
        self.next_state = next_state
        super().__init__(
            f"illegal_order_state_transition:{current_state.value}->{next_state.value}"
        )


class OrderStateNotFoundError(RuntimeError):
    pass


_VALID_TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.NEW: {
        OrderState.SENT,
        OrderState.REJECTED,
        OrderState.CANCELLED,
        OrderState.EXPIRED,
    },
    OrderState.SENT: {
        OrderState.ACKNOWLEDGED,
        OrderState.PARTIAL,
        OrderState.FILLED,
        OrderState.REJECTED,
        OrderState.CANCELLED,
        OrderState.EXPIRED,
    },
    OrderState.ACKNOWLEDGED: {
        OrderState.PARTIAL,
        OrderState.FILLED,
        OrderState.REJECTED,
        OrderState.CANCELLED,
        OrderState.EXPIRED,
    },
    OrderState.PARTIAL: {
        OrderState.PARTIAL,
        OrderState.FILLED,
        OrderState.REJECTED,
        OrderState.CANCELLED,
        OrderState.EXPIRED,
    },
    OrderState.FILLED: set(),
    OrderState.REJECTED: set(),
    OrderState.CANCELLED: set(),
    OrderState.EXPIRED: set(),
}


@dataclass(frozen=True)
class OrderRecord:
    order_id: str
    idempotency_key: str
    state: OrderState
    created_at: float
    updated_at: float
    broker_order_id: str | None
    instrument: str | None = None
    side: str | None = None
    quantity: float = 0.0
    filled_qty: float = 0.0
    avg_fill_price: float | None = None


@dataclass(frozen=True)
class OrderStateEvent:
    event_id: int
    order_id: str
    idempotency_key: str
    from_state: OrderState | None
    to_state: OrderState
    reason: str | None
    broker_order_id: str | None
    created_at: float
    filled_qty: float | None = None


class OrderStateMachine:
    _write_lock = threading.RLock()

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(str(db_path or getattr(cfg, "TRADE_DB_PATH", "data/trades.db")))
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self._db_path),
            timeout=10.0,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._write_lock:
            with self._conn() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=FULL")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS order_states (
                        order_id TEXT PRIMARY KEY,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        instrument TEXT,
                        side TEXT,
                        quantity REAL NOT NULL DEFAULT 0,
                        state TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        broker_order_id TEXT,
                        filled_qty REAL NOT NULL DEFAULT 0,
                        avg_fill_price REAL,
                        CHECK(state IN ('NEW','SENT','ACKNOWLEDGED','PARTIAL','FILLED','REJECTED','CANCELLED','EXPIRED'))
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS orders (
                        order_id TEXT PRIMARY KEY,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        instrument TEXT,
                        side TEXT,
                        quantity REAL NOT NULL DEFAULT 0,
                        state TEXT NOT NULL,
                        filled_qty REAL NOT NULL DEFAULT 0,
                        avg_fill_price REAL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        broker_order_id TEXT,
                        CHECK(state IN ('NEW','SENT','ACKNOWLEDGED','PARTIAL','FILLED','REJECTED','CANCELLED','EXPIRED'))
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS order_state_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        from_state TEXT,
                        to_state TEXT NOT NULL,
                        reason TEXT,
                        broker_order_id TEXT,
                        filled_qty REAL,
                        created_at REAL NOT NULL,
                        CHECK(to_state IN ('NEW','SENT','ACKNOWLEDGED','PARTIAL','FILLED','REJECTED','CANCELLED','EXPIRED')),
                        FOREIGN KEY(order_id) REFERENCES order_states(order_id)
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_order_state_events_order_id ON order_state_events(order_id, id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_order_states_idempotency_key ON order_states(idempotency_key)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_order_states_broker_order_id ON order_states(broker_order_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_order_states_state ON order_states(state)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_orders_idempotency_key ON orders(idempotency_key)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_orders_state ON orders(state)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_orders_updated_at ON orders(updated_at DESC)"
                )
                try:
                    conn.execute("ALTER TABLE order_states ADD COLUMN filled_qty REAL NOT NULL DEFAULT 0")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE order_states ADD COLUMN instrument TEXT")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE order_states ADD COLUMN side TEXT")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE order_states ADD COLUMN quantity REAL NOT NULL DEFAULT 0")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE order_states ADD COLUMN avg_fill_price REAL")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE order_state_events ADD COLUMN filled_qty REAL")
                except Exception:
                    pass
                conn.execute(
                    """
                    INSERT OR REPLACE INTO orders (
                        order_id,
                        idempotency_key,
                        instrument,
                        side,
                        quantity,
                        state,
                        filled_qty,
                        avg_fill_price,
                        created_at,
                        updated_at,
                        broker_order_id
                    )
                    SELECT
                        order_id,
                        idempotency_key,
                        instrument,
                        side,
                        quantity,
                        state,
                        filled_qty,
                        avg_fill_price,
                        created_at,
                        updated_at,
                        broker_order_id
                    FROM order_states
                    """
                )
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_order_states_ai_to_orders
                    AFTER INSERT ON order_states
                    BEGIN
                        INSERT OR REPLACE INTO orders (
                            order_id,
                            idempotency_key,
                            instrument,
                            side,
                            quantity,
                            state,
                            filled_qty,
                            avg_fill_price,
                            created_at,
                            updated_at,
                            broker_order_id
                        ) VALUES (
                            NEW.order_id,
                            NEW.idempotency_key,
                            NEW.instrument,
                            NEW.side,
                            NEW.quantity,
                            NEW.state,
                            NEW.filled_qty,
                            NEW.avg_fill_price,
                            NEW.created_at,
                            NEW.updated_at,
                            NEW.broker_order_id
                        );
                    END
                    """
                )
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_order_states_au_to_orders
                    AFTER UPDATE ON order_states
                    BEGIN
                        INSERT OR REPLACE INTO orders (
                            order_id,
                            idempotency_key,
                            instrument,
                            side,
                            quantity,
                            state,
                            filled_qty,
                            avg_fill_price,
                            created_at,
                            updated_at,
                            broker_order_id
                        ) VALUES (
                            NEW.order_id,
                            NEW.idempotency_key,
                            NEW.instrument,
                            NEW.side,
                            NEW.quantity,
                            NEW.state,
                            NEW.filled_qty,
                            NEW.avg_fill_price,
                            NEW.created_at,
                            NEW.updated_at,
                            NEW.broker_order_id
                        );
                    END
                    """
                )
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_order_states_ad_to_orders
                    AFTER DELETE ON order_states
                    BEGIN
                        DELETE FROM orders WHERE order_id = OLD.order_id;
                    END
                    """
                )

    @staticmethod
    def _normalize_side(value: str | None) -> str | None:
        text = str(value or "").strip().upper()
        if not text:
            return None
        if text in {"BUY", "SELL"}:
            return text
        return text

    @staticmethod
    def _coerce_state(value: OrderState | str) -> OrderState:
        if isinstance(value, OrderState):
            return value
        return OrderState(str(value).strip().upper())

    @classmethod
    def valid_next_states(cls, state: OrderState | str) -> tuple[OrderState, ...]:
        current = cls._coerce_state(state)
        out = tuple(sorted(_VALID_TRANSITIONS[current], key=lambda s: s.value))
        return out

    @classmethod
    def is_transition_valid(
        cls,
        current_state: OrderState | str,
        next_state: OrderState | str,
    ) -> bool:
        current = cls._coerce_state(current_state)
        nxt = cls._coerce_state(next_state)
        return nxt in _VALID_TRANSITIONS[current]

    @classmethod
    def validate_transition(
        cls,
        current_state: OrderState | str,
        next_state: OrderState | str,
    ) -> None:
        current = cls._coerce_state(current_state)
        nxt = cls._coerce_state(next_state)
        if not cls.is_transition_valid(current, nxt):
            raise OrderStateTransitionError(current, nxt)

    @staticmethod
    def _row_to_record(row: sqlite3.Row | None) -> OrderRecord | None:
        if row is None:
            return None
        keys = set(row.keys())
        filled_raw = row["filled_qty"] if "filled_qty" in keys else 0.0
        qty_raw = row["quantity"] if "quantity" in keys else 0.0
        avg_price_raw = row["avg_fill_price"] if "avg_fill_price" in keys else None
        return OrderRecord(
            order_id=str(row["order_id"]),
            idempotency_key=str(row["idempotency_key"]),
            state=OrderState(str(row["state"])),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            broker_order_id=row["broker_order_id"],
            instrument=row["instrument"] if "instrument" in keys else None,
            side=row["side"] if "side" in keys else None,
            quantity=float(qty_raw) if qty_raw is not None else 0.0,
            filled_qty=float(filled_raw) if filled_raw is not None else 0.0,
            avg_fill_price=float(avg_price_raw) if avg_price_raw is not None else None,
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> OrderStateEvent:
        from_state = row["from_state"]
        keys = set(row.keys())
        filled_raw = row["filled_qty"] if "filled_qty" in keys else None
        return OrderStateEvent(
            event_id=int(row["id"]),
            order_id=str(row["order_id"]),
            idempotency_key=str(row["idempotency_key"]),
            from_state=OrderState(str(from_state)) if from_state else None,
            to_state=OrderState(str(row["to_state"])),
            reason=row["reason"],
            broker_order_id=row["broker_order_id"],
            created_at=float(row["created_at"]),
            filled_qty=float(filled_raw) if filled_raw is not None else None,
        )

    def create_order(
        self,
        *,
        order_id: str,
        idempotency_key: str,
        instrument: str | None = None,
        side: str | None = None,
        quantity: float | None = None,
        broker_order_id: str | None = None,
        filled_qty: float | None = None,
        avg_fill_price: float | None = None,
        now_epoch: float | None = None,
    ) -> OrderRecord:
        out, _ = self.create_or_get_order(
            order_id=order_id,
            idempotency_key=idempotency_key,
            instrument=instrument,
            side=side,
            quantity=quantity,
            broker_order_id=broker_order_id,
            filled_qty=filled_qty,
            avg_fill_price=avg_fill_price,
            now_epoch=now_epoch,
        )
        return out

    def create_or_get_order(
        self,
        *,
        order_id: str,
        idempotency_key: str,
        instrument: str | None = None,
        side: str | None = None,
        quantity: float | None = None,
        broker_order_id: str | None = None,
        filled_qty: float | None = None,
        avg_fill_price: float | None = None,
        now_epoch: float | None = None,
    ) -> tuple[OrderRecord, bool]:
        oid = str(order_id or "").strip()
        idem = str(idempotency_key or "").strip()
        if not oid:
            raise ValueError("missing_order_id")
        if not idem:
            raise ValueError("missing_idempotency_key")
        inst = str(instrument or "").strip().upper() or None
        side_value = self._normalize_side(side)
        req_qty = float(quantity if quantity is not None else 0.0)
        if req_qty < 0:
            req_qty = 0.0
        qty = float(filled_qty if filled_qty is not None else 0.0)
        if qty < 0:
            qty = 0.0
        avg_fill = None if avg_fill_price is None else float(avg_fill_price)
        now_ts = float(now_epoch if now_epoch is not None else time.time())
        with self._write_lock:
            with self._conn() as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    existing_order = conn.execute(
                        "SELECT * FROM order_states WHERE order_id=?",
                        (oid,),
                    ).fetchone()
                    if existing_order is not None:
                        existing_record = self._row_to_record(existing_order)  # type: ignore[arg-type]
                        if existing_record is None:
                            raise RuntimeError(f"order_state_decode_failed:{oid}")
                        if existing_record.idempotency_key != idem:
                            raise ValueError(f"order_id_conflict:{oid}")
                        conn.execute("COMMIT")
                        return existing_record, False

                    existing_idem = conn.execute(
                        "SELECT * FROM order_states WHERE idempotency_key=?",
                        (idem,),
                    ).fetchone()
                    if existing_idem is not None:
                        conn.execute("COMMIT")
                        return self._row_to_record(existing_idem), False  # type: ignore[arg-type]

                    conn.execute(
                        """
                        INSERT INTO order_states
                        (
                            order_id,
                            idempotency_key,
                            instrument,
                            side,
                            quantity,
                            state,
                            created_at,
                            updated_at,
                            broker_order_id,
                            filled_qty,
                            avg_fill_price
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            oid,
                            idem,
                            inst,
                            side_value,
                            req_qty,
                            OrderState.NEW.value,
                            now_ts,
                            now_ts,
                            broker_order_id,
                            qty,
                            avg_fill,
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO order_state_events
                        (order_id, idempotency_key, from_state, to_state, reason, broker_order_id, created_at, filled_qty)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            oid,
                            idem,
                            None,
                            OrderState.NEW.value,
                            "order_created",
                            broker_order_id,
                            now_ts,
                            qty,
                        ),
                    )
                    row = conn.execute(
                        "SELECT * FROM order_states WHERE order_id=?",
                        (oid,),
                    ).fetchone()
                    conn.execute("COMMIT")
                    return self._row_to_record(row), True  # type: ignore[arg-type]
                except Exception:
                    conn.execute("ROLLBACK")
                    raise

    def get_order_by_idempotency_key(self, idempotency_key: str) -> OrderRecord | None:
        idem = str(idempotency_key or "").strip()
        if not idem:
            raise ValueError("missing_idempotency_key")
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM order_states WHERE idempotency_key=?",
                (idem,),
            ).fetchone()
        return self._row_to_record(row)

    def get_order_by_broker_order_id(self, broker_order_id: str) -> OrderRecord | None:
        broker_id = str(broker_order_id or "").strip()
        if not broker_id:
            raise ValueError("missing_broker_order_id")
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM order_states WHERE broker_order_id=? ORDER BY updated_at DESC LIMIT 1",
                (broker_id,),
            ).fetchone()
        return self._row_to_record(row)

    def list_orders(
        self,
        *,
        states: Iterable[OrderState | str] | None = None,
        include_terminal: bool = True,
        limit: int = 2000,
    ) -> list[OrderRecord]:
        lim = int(limit if limit is not None else 2000)
        if lim <= 0:
            lim = 2000
        with self._conn() as conn:
            if states:
                normalized = [self._coerce_state(x).value for x in states]
                placeholders = ",".join("?" for _ in normalized)
                rows = conn.execute(
                    f"SELECT * FROM order_states WHERE state IN ({placeholders}) ORDER BY updated_at DESC LIMIT ?",
                    (*normalized, lim),
                ).fetchall()
            elif include_terminal:
                rows = conn.execute(
                    "SELECT * FROM order_states ORDER BY updated_at DESC LIMIT ?",
                    (lim,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM order_states
                    WHERE state NOT IN ('FILLED','REJECTED','CANCELLED','EXPIRED')
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (lim,),
                ).fetchall()
        out: list[OrderRecord] = []
        for row in rows:
            rec = self._row_to_record(row)
            if rec is not None:
                out.append(rec)
        return out

    def get_order(self, order_id: str) -> OrderRecord:
        oid = str(order_id or "").strip()
        if not oid:
            raise ValueError("missing_order_id")
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM order_states WHERE order_id=?",
                (oid,),
            ).fetchone()
        rec = self._row_to_record(row)
        if rec is None:
            raise OrderStateNotFoundError(f"order_not_found:{oid}")
        return rec

    def list_events(self, order_id: str) -> list[OrderStateEvent]:
        oid = str(order_id or "").strip()
        if not oid:
            raise ValueError("missing_order_id")
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, order_id, idempotency_key, from_state, to_state, reason, broker_order_id, created_at, filled_qty
                FROM order_state_events
                WHERE order_id=?
                ORDER BY id ASC
                """,
                (oid,),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def transition(
        self,
        *,
        order_id: str,
        next_state: OrderState | str,
        broker_order_id: str | None = None,
        reason: str | None = None,
        filled_qty: float | None = None,
        avg_fill_price: float | None = None,
        now_epoch: float | None = None,
    ) -> OrderRecord:
        oid = str(order_id or "").strip()
        if not oid:
            raise ValueError("missing_order_id")
        nxt = self._coerce_state(next_state)
        now_ts = float(now_epoch if now_epoch is not None else time.time())
        with self._write_lock:
            with self._conn() as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    row = conn.execute(
                        "SELECT * FROM order_states WHERE order_id=?",
                        (oid,),
                    ).fetchone()
                    current = self._row_to_record(row)
                    if current is None:
                        raise OrderStateNotFoundError(f"order_not_found:{oid}")

                    self.validate_transition(current.state, nxt)

                    broker_id = (
                        broker_order_id
                        if broker_order_id is not None
                        else current.broker_order_id
                    )
                    qty = current.filled_qty if filled_qty is None else float(filled_qty)
                    if qty < 0:
                        qty = 0.0
                    avg_fill = (
                        current.avg_fill_price
                        if avg_fill_price is None
                        else float(avg_fill_price)
                    )
                    conn.execute(
                        """
                        UPDATE order_states
                        SET state=?, updated_at=?, broker_order_id=?, filled_qty=?, avg_fill_price=?
                        WHERE order_id=?
                        """,
                        (nxt.value, now_ts, broker_id, qty, avg_fill, oid),
                    )
                    conn.execute(
                        """
                        INSERT INTO order_state_events
                        (order_id, idempotency_key, from_state, to_state, reason, broker_order_id, created_at, filled_qty)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            current.order_id,
                            current.idempotency_key,
                            current.state.value,
                            nxt.value,
                            reason,
                            broker_id,
                            now_ts,
                            qty,
                        ),
                    )
                    out_row = conn.execute(
                        "SELECT * FROM order_states WHERE order_id=?",
                        (oid,),
                    ).fetchone()
                    conn.execute("COMMIT")
                    return self._row_to_record(out_row)  # type: ignore[arg-type]
                except Exception:
                    conn.execute("ROLLBACK")
                    raise

    def set_filled_quantity(
        self,
        *,
        order_id: str,
        filled_qty: float,
        reason: str | None = None,
        now_epoch: float | None = None,
    ) -> OrderRecord:
        oid = str(order_id or "").strip()
        if not oid:
            raise ValueError("missing_order_id")
        qty = float(filled_qty)
        if qty < 0:
            qty = 0.0
        now_ts = float(now_epoch if now_epoch is not None else time.time())
        with self._write_lock:
            with self._conn() as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    row = conn.execute(
                        "SELECT * FROM order_states WHERE order_id=?",
                        (oid,),
                    ).fetchone()
                    current = self._row_to_record(row)
                    if current is None:
                        raise OrderStateNotFoundError(f"order_not_found:{oid}")
                    if abs(float(current.filled_qty) - qty) < 1e-9:
                        conn.execute("COMMIT")
                        return current
                    conn.execute(
                        "UPDATE order_states SET filled_qty=?, updated_at=? WHERE order_id=?",
                        (qty, now_ts, oid),
                    )
                    conn.execute(
                        """
                        INSERT INTO order_state_events
                        (order_id, idempotency_key, from_state, to_state, reason, broker_order_id, created_at, filled_qty)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            current.order_id,
                            current.idempotency_key,
                            current.state.value,
                            current.state.value,
                            reason or "fill_qty_updated",
                            current.broker_order_id,
                            now_ts,
                            qty,
                        ),
                    )
                    out_row = conn.execute(
                        "SELECT * FROM order_states WHERE order_id=?",
                        (oid,),
                    ).fetchone()
                    conn.execute("COMMIT")
                    return self._row_to_record(out_row)  # type: ignore[arg-type]
                except Exception:
                    conn.execute("ROLLBACK")
                    raise


def iter_terminal_states() -> Iterable[OrderState]:
    return (
        OrderState.FILLED,
        OrderState.REJECTED,
        OrderState.CANCELLED,
        OrderState.EXPIRED,
    )
