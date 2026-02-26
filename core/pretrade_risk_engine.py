"""Migration note:
Pre-trade risk checks for execution-time order gating with durable SQLite
state for rate limiting and duplicate-signal detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

from config import config as cfg


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _normalize_instrument(value: Any) -> str:
    out = str(value or "").strip().upper()
    return out or "UNKNOWN"


def _normalize_side(value: Any) -> str:
    out = str(value or "").strip().upper()
    return out or "UNKNOWN"


@dataclass(frozen=True)
class PreTradeRiskRequest:
    signal_id: str
    instrument: str
    side: str
    quantity: float
    timestamp: float
    exposure: float = 0.0
    margin_required: float | None = None


@dataclass(frozen=True)
class PreTradeRiskDecision:
    allowed: bool
    reason_code: str
    reason: str
    checks: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": bool(self.allowed),
            "reason_code": str(self.reason_code),
            "reason": str(self.reason),
            "checks": list(self.checks or []),
            "context": dict(self.context or {}),
        }


class PreTradeRiskEngine:
    _lock = threading.RLock()

    def __init__(self, db_path: str | Path | None = None, now_fn=None):
        self._db_path = Path(str(db_path or getattr(cfg, "TRADE_DB_PATH", "data/trades.db")))
        self._now_fn = now_fn if callable(now_fn) else time.time
        self.enabled = bool(getattr(cfg, "PRETRADE_RISK_ENABLE", True))
        self.margin_buffer_pct = max(0.0, float(getattr(cfg, "PRETRADE_MARGIN_BUFFER_PCT", 0.05)))
        self.max_exposure_per_instrument = float(
            getattr(cfg, "PRETRADE_MAX_EXPOSURE_PER_INSTRUMENT", 1_000_000_000.0)
        )
        self.max_daily_loss = float(
            getattr(
                cfg,
                "PRETRADE_MAX_DAILY_LOSS",
                getattr(cfg, "DAILY_LOSS_LIMIT", 1_000_000_000.0),
            )
        )
        self.max_trades_per_minute = max(
            1, int(getattr(cfg, "PRETRADE_MAX_TRADES_PER_MINUTE", 20))
        )
        self.max_correlated_exposure = float(
            getattr(cfg, "PRETRADE_MAX_CORRELATED_EXPOSURE", 1_000_000_000.0)
        )
        self.duplicate_window_sec = max(
            0.0, float(getattr(cfg, "PRETRADE_DUPLICATE_WINDOW_SEC", 300.0))
        )
        self.correlation_threshold = float(
            getattr(cfg, "PRETRADE_CORRELATION_THRESHOLD", 0.75)
        )
        self.require_margin_data = _to_bool(
            getattr(cfg, "PRETRADE_REQUIRE_MARGIN_DATA", False), False
        )
        self.require_daily_loss_data = _to_bool(
            getattr(cfg, "PRETRADE_REQUIRE_DAILY_LOSS_DATA", False), False
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

    def _init_db(self) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=FULL")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pretrade_risk_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts_epoch REAL NOT NULL,
                        signal_id TEXT,
                        instrument TEXT NOT NULL,
                        side TEXT NOT NULL,
                        quantity REAL NOT NULL DEFAULT 0,
                        exposure REAL NOT NULL DEFAULT 0,
                        decision TEXT NOT NULL,
                        reason_code TEXT NOT NULL,
                        order_id TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pretrade_signal_registry (
                        signal_id TEXT NOT NULL,
                        instrument TEXT NOT NULL,
                        side TEXT NOT NULL,
                        last_seen_ts REAL NOT NULL,
                        hits INTEGER NOT NULL DEFAULT 1,
                        PRIMARY KEY (signal_id, instrument, side)
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_pretrade_risk_events_ts ON pretrade_risk_events(ts_epoch DESC)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_pretrade_risk_events_decision_ts ON pretrade_risk_events(decision, ts_epoch DESC)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_pretrade_signal_registry_last_seen ON pretrade_signal_registry(last_seen_ts DESC)"
                )

    @staticmethod
    def _normalize_request(request: PreTradeRiskRequest) -> PreTradeRiskRequest:
        return PreTradeRiskRequest(
            signal_id=str(request.signal_id or "").strip(),
            instrument=_normalize_instrument(request.instrument),
            side=_normalize_side(request.side),
            quantity=max(0.0, _to_float(request.quantity, 0.0)),
            timestamp=_to_float(request.timestamp, 0.0),
            exposure=max(0.0, _to_float(request.exposure, 0.0)),
            margin_required=(
                None
                if request.margin_required is None
                else max(0.0, _to_float(request.margin_required, 0.0))
            ),
        )

    @staticmethod
    def _coerce_exposure_map(value: Any) -> dict[str, float]:
        out: dict[str, float] = {}
        if not isinstance(value, dict):
            return out
        for key, raw in value.items():
            inst = _normalize_instrument(key)
            out[inst] = max(0.0, _to_float(raw, 0.0))
        return out

    @staticmethod
    def _normalize_correlations(raw: Any) -> dict[tuple[str, str], float]:
        out: dict[tuple[str, str], float] = {}
        if not isinstance(raw, dict):
            return out
        for key, value in raw.items():
            corr = _to_float(value, 0.0)
            if isinstance(key, (tuple, list)) and len(key) == 2:
                a = _normalize_instrument(key[0])
                b = _normalize_instrument(key[1])
                out[tuple(sorted((a, b)))] = corr
            elif isinstance(key, str):
                parts = key.replace("|", ",").replace(":", ",").split(",")
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) == 2:
                    a = _normalize_instrument(parts[0])
                    b = _normalize_instrument(parts[1])
                    out[tuple(sorted((a, b)))] = corr
        return out

    def _lookup_duplicate_signal(
        self,
        signal_id: str,
        instrument: str,
        side: str,
        now_epoch: float,
    ) -> tuple[bool, float | None]:
        if not signal_id:
            return False, None
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT last_seen_ts
                FROM pretrade_signal_registry
                WHERE signal_id=? AND instrument=? AND side=?
                """,
                (signal_id, instrument, side),
            ).fetchone()
        if row is None:
            return False, None
        last_seen = _to_float(row["last_seen_ts"], 0.0)
        if self.duplicate_window_sec <= 0:
            return False, last_seen
        return (now_epoch - last_seen) <= self.duplicate_window_sec, last_seen

    def _recent_accepted_trade_count(self, now_epoch: float, window_sec: float = 60.0) -> int:
        cutoff = float(now_epoch) - max(0.0, float(window_sec))
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(1) AS c
                FROM pretrade_risk_events
                WHERE decision='ACCEPTED' AND ts_epoch>=?
                """,
                (cutoff,),
            ).fetchone()
        return int(row["c"]) if row is not None else 0

    def record_decision(
        self,
        request: PreTradeRiskRequest,
        *,
        accepted: bool,
        reason_code: str,
        order_id: str | None = None,
        now_epoch: float | None = None,
    ) -> None:
        req = self._normalize_request(request)
        now_ts = _to_float(now_epoch, _to_float(self._now_fn(), 0.0))
        decision_text = "ACCEPTED" if accepted else "REJECTED"
        with self._lock:
            with self._conn() as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(
                        """
                        INSERT INTO pretrade_risk_events
                        (ts_epoch, signal_id, instrument, side, quantity, exposure, decision, reason_code, order_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            now_ts,
                            req.signal_id,
                            req.instrument,
                            req.side,
                            req.quantity,
                            req.exposure,
                            decision_text,
                            str(reason_code or "UNKNOWN"),
                            str(order_id) if order_id is not None else None,
                        ),
                    )
                    if accepted and req.signal_id:
                        existing = conn.execute(
                            """
                            SELECT hits
                            FROM pretrade_signal_registry
                            WHERE signal_id=? AND instrument=? AND side=?
                            """,
                            (req.signal_id, req.instrument, req.side),
                        ).fetchone()
                        if existing is None:
                            conn.execute(
                                """
                                INSERT INTO pretrade_signal_registry
                                (signal_id, instrument, side, last_seen_ts, hits)
                                VALUES (?, ?, ?, ?, ?)
                                """,
                                (req.signal_id, req.instrument, req.side, now_ts, 1),
                            )
                        else:
                            conn.execute(
                                """
                                UPDATE pretrade_signal_registry
                                SET last_seen_ts=?, hits=hits+1
                                WHERE signal_id=? AND instrument=? AND side=?
                                """,
                                (now_ts, req.signal_id, req.instrument, req.side),
                            )
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise

    def evaluate(
        self,
        request: PreTradeRiskRequest,
        *,
        context: dict[str, Any] | None = None,
    ) -> PreTradeRiskDecision:
        req = self._normalize_request(request)
        ctx = dict(context or {})
        now_epoch = _to_float(ctx.get("now_epoch"), _to_float(self._now_fn(), 0.0))
        checks: list[dict[str, Any]] = []

        if not self.enabled:
            return PreTradeRiskDecision(
                allowed=True,
                reason_code="PRETRADE_RISK_DISABLED",
                reason="pretrade_risk_disabled",
                checks=[
                    {
                        "name": "pretrade_risk_enabled",
                        "passed": True,
                        "reason_code": "PRETRADE_RISK_DISABLED",
                    }
                ],
                context={"instrument": req.instrument, "side": req.side},
            )

        def _fail(
            *,
            reason_code: str,
            reason: str,
            details: dict[str, Any] | None = None,
        ) -> PreTradeRiskDecision:
            if details is None:
                details = {}
            return PreTradeRiskDecision(
                allowed=False,
                reason_code=str(reason_code),
                reason=str(reason),
                checks=list(checks),
                context={
                    "signal_id": req.signal_id,
                    "instrument": req.instrument,
                    "side": req.side,
                    "quantity": req.quantity,
                    "exposure": req.exposure,
                    "details": dict(details),
                },
            )

        margin_required = req.margin_required
        if margin_required is None:
            margin_required = _to_float(ctx.get("margin_required"), req.exposure)
        margin_required = max(0.0, _to_float(margin_required, 0.0))
        margin_available_raw = ctx.get("margin_available")
        if margin_required > 0:
            if margin_available_raw is None:
                checks.append(
                    {
                        "name": "margin_availability",
                        "passed": not self.require_margin_data,
                        "reason_code": (
                            "MARGIN_DATA_MISSING" if self.require_margin_data else "SKIPPED"
                        ),
                        "required": margin_required,
                    }
                )
                if self.require_margin_data:
                    return _fail(
                        reason_code="MARGIN_DATA_MISSING",
                        reason="margin_data_missing",
                        details={"margin_required": margin_required},
                    )
            else:
                margin_available = max(0.0, _to_float(margin_available_raw, 0.0))
                buffered_margin = margin_required * (1.0 + self.margin_buffer_pct)
                passed = margin_available >= buffered_margin
                checks.append(
                    {
                        "name": "margin_availability",
                        "passed": passed,
                        "reason_code": "OK" if passed else "INSUFFICIENT_MARGIN",
                        "margin_available": margin_available,
                        "margin_required": margin_required,
                        "margin_required_buffered": buffered_margin,
                    }
                )
                if not passed:
                    return _fail(
                        reason_code="INSUFFICIENT_MARGIN",
                        reason="insufficient_margin",
                        details={
                            "margin_available": margin_available,
                            "margin_required": margin_required,
                            "margin_required_buffered": buffered_margin,
                        },
                    )
        else:
            checks.append(
                {
                    "name": "margin_availability",
                    "passed": True,
                    "reason_code": "SKIPPED",
                    "margin_required": margin_required,
                }
            )

        exposure_map = self._coerce_exposure_map(
            ctx.get("current_exposure_by_instrument")
        )
        current_exposure = max(0.0, _to_float(exposure_map.get(req.instrument), 0.0))
        projected_exposure = current_exposure + max(0.0, req.exposure)
        max_per_instrument = _to_float(
            ctx.get("max_exposure_per_instrument"),
            self.max_exposure_per_instrument,
        )
        exposure_ok = projected_exposure <= max_per_instrument
        checks.append(
            {
                "name": "max_exposure_per_instrument",
                "passed": exposure_ok,
                "reason_code": "OK" if exposure_ok else "MAX_EXPOSURE_PER_INSTRUMENT",
                "current_exposure": current_exposure,
                "requested_exposure": req.exposure,
                "projected_exposure": projected_exposure,
                "max_exposure_per_instrument": max_per_instrument,
            }
        )
        if not exposure_ok:
            return _fail(
                reason_code="MAX_EXPOSURE_PER_INSTRUMENT",
                reason="max_exposure_per_instrument_breached",
                details={
                    "projected_exposure": projected_exposure,
                    "max_exposure_per_instrument": max_per_instrument,
                },
            )

        daily_loss_value = ctx.get("daily_loss")
        if daily_loss_value is None:
            daily_pnl = ctx.get("daily_pnl")
            if daily_pnl is not None:
                pnl_val = _to_float(daily_pnl, 0.0)
                daily_loss_value = abs(pnl_val) if pnl_val < 0 else 0.0
        if daily_loss_value is None:
            checks.append(
                {
                    "name": "max_daily_loss",
                    "passed": not self.require_daily_loss_data,
                    "reason_code": (
                        "DAILY_LOSS_DATA_MISSING" if self.require_daily_loss_data else "SKIPPED"
                    ),
                }
            )
            if self.require_daily_loss_data:
                return _fail(
                    reason_code="DAILY_LOSS_DATA_MISSING",
                    reason="daily_loss_data_missing",
                )
            daily_loss_abs = 0.0
        else:
            daily_loss_abs = max(0.0, _to_float(daily_loss_value, 0.0))
            max_daily_loss = _to_float(ctx.get("max_daily_loss"), self.max_daily_loss)
            daily_loss_ok = daily_loss_abs < max_daily_loss
            checks.append(
                {
                    "name": "max_daily_loss",
                    "passed": daily_loss_ok,
                    "reason_code": "OK" if daily_loss_ok else "MAX_DAILY_LOSS",
                    "daily_loss": daily_loss_abs,
                    "max_daily_loss": max_daily_loss,
                }
            )
            if not daily_loss_ok:
                return _fail(
                    reason_code="MAX_DAILY_LOSS",
                    reason="max_daily_loss_breached",
                    details={"daily_loss": daily_loss_abs, "max_daily_loss": max_daily_loss},
                )

        trades_last_minute = ctx.get("trades_last_minute")
        if trades_last_minute is None:
            trades_last_minute = self._recent_accepted_trade_count(now_epoch, 60.0)
        trades_last_minute = max(0, _to_int(trades_last_minute, 0))
        max_trades_pm = max(
            1, _to_int(ctx.get("max_trades_per_minute"), self.max_trades_per_minute)
        )
        trades_rate_ok = trades_last_minute < max_trades_pm
        checks.append(
            {
                "name": "max_trades_per_minute",
                "passed": trades_rate_ok,
                "reason_code": "OK" if trades_rate_ok else "MAX_TRADES_PER_MINUTE",
                "trades_last_minute": trades_last_minute,
                "max_trades_per_minute": max_trades_pm,
            }
        )
        if not trades_rate_ok:
            return _fail(
                reason_code="MAX_TRADES_PER_MINUTE",
                reason="max_trades_per_minute_breached",
                details={
                    "trades_last_minute": trades_last_minute,
                    "max_trades_per_minute": max_trades_pm,
                },
            )

        correlation_threshold = _to_float(
            ctx.get("correlation_threshold"),
            self.correlation_threshold,
        )
        max_corr_exposure = _to_float(
            ctx.get("max_correlated_exposure"),
            self.max_correlated_exposure,
        )
        corr_map = self._normalize_correlations(
            ctx.get("correlations", getattr(cfg, "SYMBOL_CORRELATIONS", {}))
        )
        correlated_current = 0.0
        for instrument, value in exposure_map.items():
            if instrument == req.instrument:
                correlated_current += max(0.0, value)
                continue
            key = tuple(sorted((req.instrument, instrument)))
            corr = _to_float(corr_map.get(key), 0.0)
            if corr >= correlation_threshold:
                correlated_current += max(0.0, value)
        correlated_projected = correlated_current + max(0.0, req.exposure)
        correlated_ok = correlated_projected <= max_corr_exposure
        checks.append(
            {
                "name": "correlated_exposure_limit",
                "passed": correlated_ok,
                "reason_code": "OK" if correlated_ok else "CORRELATED_EXPOSURE_LIMIT",
                "correlated_current_exposure": correlated_current,
                "requested_exposure": req.exposure,
                "projected_correlated_exposure": correlated_projected,
                "max_correlated_exposure": max_corr_exposure,
                "correlation_threshold": correlation_threshold,
            }
        )
        if not correlated_ok:
            return _fail(
                reason_code="CORRELATED_EXPOSURE_LIMIT",
                reason="correlated_exposure_limit_breached",
                details={
                    "projected_correlated_exposure": correlated_projected,
                    "max_correlated_exposure": max_corr_exposure,
                },
            )

        duplicate, last_seen_ts = self._lookup_duplicate_signal(
            req.signal_id,
            req.instrument,
            req.side,
            now_epoch,
        )
        checks.append(
            {
                "name": "duplicate_signal_detection",
                "passed": not duplicate,
                "reason_code": "OK" if not duplicate else "DUPLICATE_SIGNAL",
                "duplicate_window_sec": self.duplicate_window_sec,
                "last_seen_ts": last_seen_ts,
            }
        )
        if duplicate:
            return _fail(
                reason_code="DUPLICATE_SIGNAL",
                reason="duplicate_signal_detected",
                details={
                    "signal_id": req.signal_id,
                    "last_seen_ts": last_seen_ts,
                    "duplicate_window_sec": self.duplicate_window_sec,
                },
            )

        return PreTradeRiskDecision(
            allowed=True,
            reason_code="OK",
            reason="pretrade_checks_passed",
            checks=checks,
            context={
                "signal_id": req.signal_id,
                "instrument": req.instrument,
                "side": req.side,
                "quantity": req.quantity,
                "exposure": req.exposure,
                "daily_loss": daily_loss_abs,
                "trades_last_minute": trades_last_minute,
            },
        )

