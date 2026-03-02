"""Migration note:
Persistent per-instrument execution performance tracking with rolling-window
metrics and automatic cooldown gating.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

from config import config as cfg
from core.paths import db_dir, logs_dir


_COMPLETION_STATES = {"PARTIAL", "FILLED", "REJECTED", "CANCELLED", "EXPIRED"}


def _to_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _normalize_instrument(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text or "UNKNOWN"


@dataclass(frozen=True)
class InstrumentExecutionMetrics:
    instrument: str
    sample_size: int
    fill_rate: float
    avg_slippage: float | None
    rejection_rate: float
    avg_time_to_fill: float | None
    partial_fill_ratio: float
    disabled_until: float | None
    disabled: bool
    disable_reason: str | None
    updated_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument,
            "sample_size": int(self.sample_size),
            "fill_rate": float(self.fill_rate),
            "avg_slippage": self.avg_slippage,
            "rejection_rate": float(self.rejection_rate),
            "avg_time_to_fill": self.avg_time_to_fill,
            "partial_fill_ratio": float(self.partial_fill_ratio),
            "disabled_until": self.disabled_until,
            "disabled": bool(self.disabled),
            "disable_reason": self.disable_reason,
            "updated_at": float(self.updated_at),
        }


class ExecutionPerformanceTracker:
    _lock = threading.RLock()

    def __init__(self, db_path: str | Path | None = None):
        fallback_db = db_dir() / f"{getattr(cfg, 'DESK_ID', 'DEFAULT')}.sqlite"
        self._db_path = Path(str(db_path or getattr(cfg, "TRADE_DB_PATH", str(fallback_db))))
        self._window_trades = max(1, int(getattr(cfg, "EXEC_PERF_WINDOW_TRADES", 100)))
        self._min_fill_rate_pct = float(getattr(cfg, "EXEC_PERF_MIN_FILL_RATE_PCT", 60.0))
        self._max_rejection_rate_pct = float(getattr(cfg, "EXEC_PERF_MAX_REJECTION_RATE_PCT", 10.0))
        self._disable_sec = max(
            1.0, float(getattr(cfg, "EXEC_PERF_DISABLE_MINUTES", 30.0)) * 60.0
        )
        self._log_path = Path(
            str(getattr(cfg, "EXEC_PERF_LOG_PATH", str(logs_dir() / "execution_performance.jsonl")))
        )
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

    def _write_log(self, event: str, payload: dict[str, Any]) -> None:
        row = {"ts_epoch": time.time(), "event": str(event)}
        row.update(payload or {})
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        except Exception:
            pass

    def _init_db(self) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=FULL")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS execution_performance_orders (
                        order_id TEXT PRIMARY KEY,
                        instrument TEXT NOT NULL,
                        side TEXT,
                        requested_qty REAL NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL,
                        completed_at REAL,
                        state TEXT,
                        filled_qty REAL,
                        slippage REAL,
                        time_to_fill_sec REAL,
                        fill_flag INTEGER NOT NULL DEFAULT 0,
                        rejection_flag INTEGER NOT NULL DEFAULT 0,
                        partial_flag INTEGER NOT NULL DEFAULT 0,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS execution_performance_metrics (
                        instrument TEXT PRIMARY KEY,
                        sample_size INTEGER NOT NULL DEFAULT 0,
                        fill_rate_pct REAL NOT NULL DEFAULT 0,
                        avg_slippage REAL,
                        rejection_rate_pct REAL NOT NULL DEFAULT 0,
                        avg_time_to_fill_sec REAL,
                        partial_fill_ratio REAL NOT NULL DEFAULT 0,
                        disabled_until REAL,
                        disable_reason TEXT,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_exec_perf_orders_instrument_completed
                    ON execution_performance_orders(instrument, completed_at DESC)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_exec_perf_orders_updated
                    ON execution_performance_orders(updated_at DESC)
                    """
                )

    def _get_existing_metrics_row(
        self, conn: sqlite3.Connection, instrument: str
    ) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM execution_performance_metrics WHERE instrument=?",
            (instrument,),
        ).fetchone()

    def _upsert_metrics(
        self,
        conn: sqlite3.Connection,
        *,
        instrument: str,
        sample_size: int,
        fill_rate_pct: float,
        avg_slippage: float | None,
        rejection_rate_pct: float,
        avg_time_to_fill_sec: float | None,
        partial_fill_ratio: float,
        disabled_until: float | None,
        disable_reason: str | None,
        updated_at: float,
    ) -> None:
        conn.execute(
            """
            INSERT INTO execution_performance_metrics (
                instrument,
                sample_size,
                fill_rate_pct,
                avg_slippage,
                rejection_rate_pct,
                avg_time_to_fill_sec,
                partial_fill_ratio,
                disabled_until,
                disable_reason,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(instrument) DO UPDATE SET
                sample_size=excluded.sample_size,
                fill_rate_pct=excluded.fill_rate_pct,
                avg_slippage=excluded.avg_slippage,
                rejection_rate_pct=excluded.rejection_rate_pct,
                avg_time_to_fill_sec=excluded.avg_time_to_fill_sec,
                partial_fill_ratio=excluded.partial_fill_ratio,
                disabled_until=excluded.disabled_until,
                disable_reason=excluded.disable_reason,
                updated_at=excluded.updated_at
            """,
            (
                instrument,
                int(sample_size),
                float(fill_rate_pct),
                avg_slippage,
                float(rejection_rate_pct),
                avg_time_to_fill_sec,
                float(partial_fill_ratio),
                disabled_until,
                disable_reason,
                float(updated_at),
            ),
        )

    def record_order_context(
        self,
        *,
        order_id: str,
        instrument: str,
        side: str | None = None,
        requested_qty: float | None = None,
        created_at: float | None = None,
        now_epoch: float | None = None,
    ) -> None:
        oid = str(order_id or "").strip()
        if not oid:
            raise ValueError("missing_order_id")
        inst = _normalize_instrument(instrument)
        now_ts = float(now_epoch if now_epoch is not None else time.time())
        req_qty = max(0.0, float(requested_qty if requested_qty is not None else 0.0))
        created_ts = float(created_at if created_at is not None else now_ts)
        side_text = str(side or "").strip().upper() or None

        with self._lock:
            with self._conn() as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    existing = conn.execute(
                        "SELECT * FROM execution_performance_orders WHERE order_id=?",
                        (oid,),
                    ).fetchone()
                    if existing is None:
                        conn.execute(
                            """
                            INSERT INTO execution_performance_orders (
                                order_id, instrument, side, requested_qty, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (oid, inst, side_text, req_qty, created_ts, now_ts),
                        )
                    else:
                        current_instrument = _normalize_instrument(existing["instrument"])
                        current_side = str(existing["side"] or "").strip().upper() or None
                        current_requested = _to_float(existing["requested_qty"], 0.0) or 0.0
                        current_created = _to_float(existing["created_at"], created_ts) or created_ts
                        new_instrument = inst if current_instrument in {"", "UNKNOWN"} else current_instrument
                        new_side = current_side or side_text
                        new_requested = current_requested if current_requested > 0 else req_qty
                        if req_qty > 0 and current_requested <= 0:
                            new_requested = req_qty
                        new_created = min(current_created, created_ts)
                        conn.execute(
                            """
                            UPDATE execution_performance_orders
                            SET instrument=?, side=?, requested_qty=?, created_at=?, updated_at=?
                            WHERE order_id=?
                            """,
                            (new_instrument, new_side, new_requested, new_created, now_ts, oid),
                        )
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise

    def _compute_metrics_for_instrument(
        self, conn: sqlite3.Connection, instrument: str
    ) -> tuple[int, float, float | None, float, float | None, float]:
        rows = conn.execute(
            """
            SELECT fill_flag, rejection_flag, partial_flag, slippage, time_to_fill_sec
            FROM execution_performance_orders
            WHERE instrument=? AND completed_at IS NOT NULL
            ORDER BY completed_at DESC
            LIMIT ?
            """,
            (instrument, self._window_trades),
        ).fetchall()
        sample_size = len(rows)
        if sample_size == 0:
            return 0, 0.0, None, 0.0, None, 0.0

        fill_count = 0
        reject_count = 0
        partial_count = 0
        slippage_vals: list[float] = []
        ttf_vals: list[float] = []

        for row in rows:
            fill_flag = int(row["fill_flag"] or 0)
            reject_flag = int(row["rejection_flag"] or 0)
            partial_flag = int(row["partial_flag"] or 0)
            fill_count += fill_flag
            reject_count += reject_flag
            partial_count += partial_flag
            slp = _to_float(row["slippage"], None)
            if slp is not None:
                slippage_vals.append(float(slp))
            ttf = _to_float(row["time_to_fill_sec"], None)
            if ttf is not None:
                ttf_vals.append(max(0.0, float(ttf)))

        fill_rate_pct = (float(fill_count) / float(sample_size)) * 100.0
        rejection_rate_pct = (float(reject_count) / float(sample_size)) * 100.0
        avg_slippage = (
            (sum(slippage_vals) / float(len(slippage_vals))) if slippage_vals else None
        )
        avg_ttf = (sum(ttf_vals) / float(len(ttf_vals))) if ttf_vals else None
        partial_ratio = (float(partial_count) / float(fill_count)) if fill_count > 0 else 0.0
        return sample_size, fill_rate_pct, avg_slippage, rejection_rate_pct, avg_ttf, partial_ratio

    def record_order_completion(
        self,
        *,
        order_id: str,
        state: str,
        instrument: str | None = None,
        side: str | None = None,
        requested_qty: float | None = None,
        filled_qty: float | None = None,
        slippage: float | None = None,
        time_to_fill_sec: float | None = None,
        now_epoch: float | None = None,
    ) -> InstrumentExecutionMetrics:
        oid = str(order_id or "").strip()
        if not oid:
            raise ValueError("missing_order_id")
        state_text = str(state or "").strip().upper()
        if state_text not in _COMPLETION_STATES:
            raise ValueError(f"invalid_completion_state:{state_text}")

        now_ts = float(now_epoch if now_epoch is not None else time.time())
        req_override = _to_float(requested_qty, None)
        fill_override = _to_float(filled_qty, None)
        slippage_val = _to_float(slippage, None)
        ttf_override = _to_float(time_to_fill_sec, None)
        side_text = str(side or "").strip().upper() or None
        inst_override = _normalize_instrument(instrument) if instrument is not None else None

        with self._lock:
            with self._conn() as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    row = conn.execute(
                        "SELECT * FROM execution_performance_orders WHERE order_id=?",
                        (oid,),
                    ).fetchone()

                    if row is None:
                        inst = inst_override or "UNKNOWN"
                        req_qty = max(0.0, float(req_override if req_override is not None else 0.0))
                        conn.execute(
                            """
                            INSERT INTO execution_performance_orders (
                                order_id, instrument, side, requested_qty, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (oid, inst, side_text, req_qty, now_ts, now_ts),
                        )
                        row = conn.execute(
                            "SELECT * FROM execution_performance_orders WHERE order_id=?",
                            (oid,),
                        ).fetchone()

                    assert row is not None
                    existing_inst = _normalize_instrument(row["instrument"])
                    inst = inst_override or existing_inst
                    req_qty_current = _to_float(row["requested_qty"], 0.0) or 0.0
                    req_qty = req_qty_current
                    if req_override is not None and req_override > 0:
                        req_qty = float(req_override)
                    created_at = _to_float(row["created_at"], now_ts) or now_ts
                    existing_side = str(row["side"] or "").strip().upper() or None
                    side_final = existing_side or side_text

                    final_filled_qty = _to_float(row["filled_qty"], 0.0) or 0.0
                    if fill_override is not None:
                        final_filled_qty = max(0.0, float(fill_override))
                    elif state_text == "FILLED" and req_qty > 0:
                        final_filled_qty = float(req_qty)

                    fill_flag = 1 if state_text in {"PARTIAL", "FILLED"} else 0
                    reject_flag = 1 if state_text == "REJECTED" else 0
                    partial_flag = 0
                    if state_text == "PARTIAL":
                        partial_flag = 1
                    elif fill_flag and req_qty > 0 and final_filled_qty > 0 and final_filled_qty < req_qty:
                        partial_flag = 1

                    final_ttf = ttf_override
                    if final_ttf is None and fill_flag:
                        final_ttf = max(0.0, now_ts - created_at)

                    conn.execute(
                        """
                        UPDATE execution_performance_orders
                        SET
                            instrument=?,
                            side=?,
                            requested_qty=?,
                            completed_at=?,
                            state=?,
                            filled_qty=?,
                            slippage=?,
                            time_to_fill_sec=?,
                            fill_flag=?,
                            rejection_flag=?,
                            partial_flag=?,
                            updated_at=?
                        WHERE order_id=?
                        """,
                        (
                            inst,
                            side_final,
                            req_qty,
                            now_ts,
                            state_text,
                            final_filled_qty,
                            slippage_val,
                            final_ttf,
                            fill_flag,
                            reject_flag,
                            partial_flag,
                            now_ts,
                            oid,
                        ),
                    )

                    (
                        sample_size,
                        fill_rate_pct,
                        avg_slippage,
                        rejection_rate_pct,
                        avg_ttf,
                        partial_ratio,
                    ) = self._compute_metrics_for_instrument(conn, inst)

                    existing_metrics = self._get_existing_metrics_row(conn, inst)
                    old_disabled_until = (
                        _to_float(existing_metrics["disabled_until"], None)
                        if existing_metrics is not None
                        else None
                    )
                    old_disable_reason = (
                        str(existing_metrics["disable_reason"])
                        if existing_metrics is not None and existing_metrics["disable_reason"] is not None
                        else None
                    )

                    disable_reasons: list[str] = []
                    if sample_size > 0 and fill_rate_pct < self._min_fill_rate_pct:
                        disable_reasons.append("LOW_FILL_RATE")
                    if sample_size > 0 and rejection_rate_pct > self._max_rejection_rate_pct:
                        disable_reasons.append("HIGH_REJECTION_RATE")

                    disabled_until = old_disabled_until
                    disable_reason = old_disable_reason
                    if disable_reasons:
                        cooldown_until = now_ts + self._disable_sec
                        if disabled_until is None or cooldown_until > float(disabled_until):
                            disabled_until = cooldown_until
                        disable_reason = "|".join(disable_reasons)
                    else:
                        if disabled_until is not None and float(disabled_until) <= now_ts:
                            disabled_until = None
                            disable_reason = None

                    self._upsert_metrics(
                        conn,
                        instrument=inst,
                        sample_size=sample_size,
                        fill_rate_pct=fill_rate_pct,
                        avg_slippage=avg_slippage,
                        rejection_rate_pct=rejection_rate_pct,
                        avg_time_to_fill_sec=avg_ttf,
                        partial_fill_ratio=partial_ratio,
                        disabled_until=disabled_until,
                        disable_reason=disable_reason,
                        updated_at=now_ts,
                    )
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise

        out = self.get_instrument_metrics(inst, now_epoch=now_ts)
        self._write_log(
            "execution_performance_updated",
            {
                "order_id": oid,
                "instrument": inst,
                "state": state_text,
                "sample_size": out.sample_size,
                "fill_rate": out.fill_rate,
                "rejection_rate": out.rejection_rate,
                "disabled": out.disabled,
                "disabled_until": out.disabled_until,
                "disable_reason": out.disable_reason,
            },
        )
        return out

    @staticmethod
    def _metrics_from_row(row: sqlite3.Row, now_epoch: float | None = None) -> InstrumentExecutionMetrics:
        now_ts = float(now_epoch if now_epoch is not None else time.time())
        disabled_until = _to_float(row["disabled_until"], None)
        return InstrumentExecutionMetrics(
            instrument=str(row["instrument"]),
            sample_size=int(row["sample_size"] or 0),
            fill_rate=float(row["fill_rate_pct"] or 0.0),
            avg_slippage=_to_float(row["avg_slippage"], None),
            rejection_rate=float(row["rejection_rate_pct"] or 0.0),
            avg_time_to_fill=_to_float(row["avg_time_to_fill_sec"], None),
            partial_fill_ratio=float(row["partial_fill_ratio"] or 0.0),
            disabled_until=disabled_until,
            disabled=bool(disabled_until is not None and disabled_until > now_ts),
            disable_reason=row["disable_reason"],
            updated_at=float(row["updated_at"] or now_ts),
        )

    def get_instrument_metrics(
        self, instrument: str, *, now_epoch: float | None = None
    ) -> InstrumentExecutionMetrics:
        inst = _normalize_instrument(instrument)
        with self._lock:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT * FROM execution_performance_metrics WHERE instrument=?",
                    (inst,),
                ).fetchone()
        if row is None:
            now_ts = float(now_epoch if now_epoch is not None else time.time())
            return InstrumentExecutionMetrics(
                instrument=inst,
                sample_size=0,
                fill_rate=0.0,
                avg_slippage=None,
                rejection_rate=0.0,
                avg_time_to_fill=None,
                partial_fill_ratio=0.0,
                disabled_until=None,
                disabled=False,
                disable_reason=None,
                updated_at=now_ts,
            )
        return self._metrics_from_row(row, now_epoch=now_epoch)

    def list_metrics(self, *, now_epoch: float | None = None) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        with self._lock:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM execution_performance_metrics ORDER BY instrument ASC"
                ).fetchall()
        for row in rows:
            rec = self._metrics_from_row(row, now_epoch=now_epoch)
            out[rec.instrument] = rec.as_dict()
        return out

    def is_instrument_disabled(
        self, instrument: str, *, now_epoch: float | None = None
    ) -> dict[str, Any]:
        metrics = self.get_instrument_metrics(instrument, now_epoch=now_epoch)
        return {
            "instrument": metrics.instrument,
            "disabled": metrics.disabled,
            "disabled_until": metrics.disabled_until,
            "disable_reason": metrics.disable_reason,
        }
