"""Authoritative Intraday Market Session Memory Store.

Integrates both:
1. Low-overhead in-memory C1/C2 feature calculation with Parquet serialization
2. Durable SQLite/JSON session memory, snapshot context, and seal verification
"""

from __future__ import annotations

import collections
import hashlib
import json
import logging
import os
import sqlite3
import threading
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from config import config as cfg
from core.paths import db_dir, reports_dir
from core.time_utils import now_utc_epoch

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)

# =========================================================================
# Error hierarchy and utilities for durable SQLite session memory
# =========================================================================

class SessionMemoryError(RuntimeError):
    """Base exception for durable market session memory operations."""


class SessionMemoryConflict(SessionMemoryError):
    """Invalid, conflicting, or corrupt release state."""


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(IST) if value.tzinfo else value.replace(tzinfo=IST)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(IST)
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        parsed = datetime.fromisoformat(cleaned)
        return parsed.astimezone(IST) if parsed.tzinfo else parsed.replace(tzinfo=IST)
    raise SessionMemoryError(f"invalid_datetime_value:{value!r}")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _open(day: str) -> datetime:
    return datetime.combine(date.fromisoformat(day), SESSION_OPEN, tzinfo=IST)


def _close(day: str) -> datetime:
    return datetime.combine(date.fromisoformat(day), SESSION_CLOSE, tzinfo=IST)


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize(symbol: str, bar: dict[str, Any]) -> dict[str, Any]:
    required = ("timestamp", "open", "high", "low", "close", "volume")
    for key in required:
        if key not in bar:
            raise SessionMemoryError(f"bar_missing_field:{key}")
    ts = _dt(bar["timestamp"])
    o, h, l, c = _num(bar["open"]), _num(bar["high"]), _num(bar["low"]), _num(bar["close"])
    if not (l <= o <= h and l <= c <= h and l <= h):
        raise SessionMemoryError(f"bar_ohlc_invariant_violation:{bar}")
    return {
        "symbol": symbol,
        "timestamp": ts.isoformat(),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": max(0.0, _num(bar["volume"])),
        "oi": max(0.0, _num(bar.get("oi", 0.0))),
    }

# =========================================================================
# In-memory C1/C2 feature calculation structures (PR #893)
# =========================================================================

@dataclass(frozen=True)
class Bar1M:
    """Single 1-minute OHLCV bar."""
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    is_order_action: bool = False
    broker_write_authority: bool = False


@dataclass(frozen=True)
class MarketMemorySnapshot:
    """Immutable snapshot of market memory state as of a specific timestamp."""
    symbol: str
    as_of_timestamp: str
    session_date: str
    session_open: float
    last_price: float
    bars_1m_count: int
    derived_15m_bars_count: int
    rolling_15m_return_bps: float
    distance_from_session_open_bps: float
    rolling_15m_range_bps: float
    realized_vol_15m: float
    freshness_watermark: float
    persistence_watermark: float
    trace_id: str
    is_order_action: bool = False
    broker_write_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_order_action"] = False
        data["broker_write_authority"] = False
        return data


# =========================================================================
# Unified MarketSessionStore supporting both durable SQLite and fast C1/C2 in-memory evaluation
# =========================================================================

class MarketSessionStore:
    """Unified Intraday Market Session Memory Store.
    
    Provides:
    - Fast in-memory bar aggregation and rolling feature evaluation for C1/C2 evaluators
    - Durable SQLite persistence, snapshot storage, and session seal verification
    """

    def __init__(
        self,
        symbol: str = "NIFTY",
        session_date: str = "2026-09-10",
        db_path: str | Path | None = None,
        report_root: str | Path | None = None,
    ) -> None:
        self.symbol = symbol
        self.session_date = session_date
        self._bars_1m: list[Bar1M] = []
        self._derived_15m: list[dict[str, Any]] = []
        self._session_open: float | None = None
        self._last_trace_id: str = ""
        self._freshness_watermark: float = 0.0
        self._persistence_watermark: float = 0.0

        # Durable store properties
        self.db_path = Path(db_path) if db_path else db_dir() / "market_session_memory.db"
        self.report_root = Path(report_root) if report_root else reports_dir() / "market_sessions"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS completed_bars_1m (
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    oi REAL NOT NULL,
                    PRIMARY KEY (symbol, timestamp)
                );
                CREATE TABLE IF NOT EXISTS feature_snapshots (
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    features_json TEXT NOT NULL,
                    payload_sha TEXT NOT NULL,
                    PRIMARY KEY (symbol, timestamp)
                );
                CREATE TABLE IF NOT EXISTS session_seals (
                    session_date TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    payload_sha TEXT NOT NULL,
                    sealed_at TEXT NOT NULL
                );
                """
            )

    # In-memory C1/C2 methods
    @property
    def bars_count(self) -> int:
        return len(self._bars_1m)

    def session_open(self) -> float | None:
        return self._session_open

    def add_bar(self, bar: Bar1M) -> None:
        if not self._bars_1m and self._session_open is None:
            self._session_open = bar.open
        self._bars_1m.append(bar)
        self._freshness_watermark = datetime.now(timezone.utc).timestamp()
        if len(self._bars_1m) % 15 == 0:
            sub = self._bars_1m[-15:]
            self._derived_15m.append({
                "timestamp": bar.timestamp,
                "open": sub[0].open,
                "high": max(b.high for b in sub),
                "low": min(b.low for b in sub),
                "close": sub[-1].close,
                "volume": sum(b.volume for b in sub),
            })

    def get_market_memory(self, as_of_timestamp: str, trace_id: str = "") -> MarketMemorySnapshot:
        if not self._bars_1m:
            return MarketMemorySnapshot(
                symbol=self.symbol,
                as_of_timestamp=as_of_timestamp,
                session_date=self.session_date,
                session_open=0.0,
                last_price=0.0,
                bars_1m_count=0,
                derived_15m_bars_count=0,
                rolling_15m_return_bps=0.0,
                distance_from_session_open_bps=0.0,
                rolling_15m_range_bps=0.0,
                realized_vol_15m=0.0,
                freshness_watermark=self._freshness_watermark,
                persistence_watermark=self._persistence_watermark,
                trace_id=trace_id or self._last_trace_id,
            )

        last_bar = self._bars_1m[-1]
        s_open = self._session_open or last_bar.open
        dist_open_bps = ((last_bar.close - s_open) / s_open) * 10000.0 if s_open > 0 else 0.0

        if len(self._bars_1m) >= 15:
            ref_bar = self._bars_1m[-15]
            rolling_15m_ret = ((last_bar.close - ref_bar.close) / ref_bar.close) * 10000.0 if ref_bar.close > 0 else 0.0
            window = self._bars_1m[-15:]
            w_high = max(b.high for b in window)
            w_low = min(b.low for b in window)
            rolling_15m_range = ((w_high - w_low) / ref_bar.close) * 10000.0 if ref_bar.close > 0 else 0.0
            rets = [
                (window[i].close - window[i - 1].close) / window[i - 1].close
                for i in range(1, len(window))
                if window[i - 1].close > 0
            ]
            realized_vol = float(np.std(rets) * np.sqrt(375)) if len(rets) > 1 else 0.0
        else:
            rolling_15m_ret = 0.0
            rolling_15m_range = 0.0
            realized_vol = 0.0

        return MarketMemorySnapshot(
            symbol=self.symbol,
            as_of_timestamp=as_of_timestamp,
            session_date=self.session_date,
            session_open=s_open,
            last_price=last_bar.close,
            bars_1m_count=len(self._bars_1m),
            derived_15m_bars_count=len(self._derived_15m),
            rolling_15m_return_bps=rolling_15m_ret,
            distance_from_session_open_bps=dist_open_bps,
            rolling_15m_range_bps=rolling_15m_range,
            realized_vol_15m=realized_vol,
            freshness_watermark=self._freshness_watermark,
            persistence_watermark=self._persistence_watermark,
            trace_id=trace_id or self._last_trace_id,
        )

    def to_dataframe(self) -> pd.DataFrame:
        records = [
            {
                "timestamp": b.timestamp,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in self._bars_1m
        ]
        return pd.DataFrame(records)

    def persist_to_parquet(self, filepath: str | Path) -> str:
        df = self.to_dataframe()
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(p, index=False)
        self._persistence_watermark = datetime.now(timezone.utc).timestamp()
        return str(p)

    @classmethod
    def load_from_parquet(cls, filepath: str | Path, symbol: str = "NIFTY", session_date: str = "2026-09-10") -> MarketSessionStore:
        p = Path(filepath)
        if not p.exists():
            raise FileNotFoundError(f"parquet_store_not_found: {filepath}")
        df = pd.read_parquet(p)
        store = cls(symbol=symbol, session_date=session_date)
        for _, row in df.iterrows():
            bar = Bar1M(
                timestamp=str(row["timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
            )
            store.add_bar(bar)
        return store

    # Durable SQLite methods
    def persist_completed_bar(self, symbol: str, bar: dict[str, Any]) -> dict[str, Any]:
        norm = _normalize(symbol, bar)
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO completed_bars_1m (symbol, timestamp, open, high, low, close, volume, oi)
                VALUES (:symbol, :timestamp, :open, :high, :low, :close, :volume, :oi)
                ON CONFLICT(symbol, timestamp) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
                    volume=excluded.volume, oi=excluded.oi;
                """,
                norm,
            )
        return norm

    def _load(self, day: str, symbol: str) -> list[dict[str, Any]]:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                """
                SELECT timestamp, open, high, low, close, volume, oi FROM completed_bars_1m
                WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC;
                """,
                (symbol, _open(day).isoformat(), _close(day).isoformat()),
            )
            return [dict(row) for row in cur.fetchall()]

    def _derive(self, bars: list[dict[str, Any]], timeframe: str, as_of: datetime) -> list[dict[str, Any]]:
        mins = {"5m": 5, "15m": 15}.get(timeframe)
        if not mins:
            raise SessionMemoryError(f"unsupported_timeframe:{timeframe}")
        buckets: dict[datetime, list[dict[str, Any]]] = collections.defaultdict(list)
        for b in bars:
            ts = _dt(b["timestamp"])
            if ts > as_of:
                continue
            delta_min = int((ts - ts.replace(hour=9, minute=15, second=0, microsecond=0)).total_seconds() // 60)
            if delta_min < 0:
                continue
            b_start = ts.replace(hour=9, minute=15, second=0, microsecond=0) + timedelta(minutes=(delta_min // mins) * mins)
            buckets[b_start].append(b)

        out: list[dict[str, Any]] = []
        for b_start in sorted(buckets.keys()):
            chunk = buckets[b_start]
            out.append({
                "timestamp": b_start.isoformat(),
                "open": chunk[0]["open"],
                "high": max(x["high"] for x in chunk),
                "low": min(x["low"] for x in chunk),
                "close": chunk[-1]["close"],
                "volume": sum(x["volume"] for x in chunk),
                "oi": chunk[-1]["oi"],
            })
        return out

    def get_bars(self, symbol: str, *, as_of: Any, timeframe: str = "1m", session_date: str | None = None) -> list[dict[str, Any]]:
        as_of_dt = _dt(as_of)
        day = session_date or as_of_dt.date().isoformat()
        bars1m = [b for b in self._load(day, symbol) if _dt(b["timestamp"]) <= as_of_dt]
        if timeframe == "1m":
            return bars1m
        return self._derive(bars1m, timeframe, as_of_dt)

    def persist_feature_snapshot(self, symbol: str, *, as_of: Any, payload: dict[str, Any]) -> dict[str, Any]:
        as_of_dt = _dt(as_of)
        body = _json(payload)
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO feature_snapshots (symbol, timestamp, features_json, payload_sha)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(symbol, timestamp) DO UPDATE SET features_json=excluded.features_json, payload_sha=excluded.payload_sha;
                """,
                (symbol, as_of_dt.isoformat(), body, sha),
            )
        return {"symbol": symbol, "timestamp": as_of_dt.isoformat(), "payload_sha": sha}

    def get_feature_snapshots(self, symbol: str, *, as_of: Any) -> list[dict[str, Any]]:
        as_of_dt = _dt(as_of)
        day = as_of_dt.date().isoformat()
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                """
                SELECT timestamp, features_json, payload_sha FROM feature_snapshots
                WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC;
                """,
                (symbol, _open(day).isoformat(), as_of_dt.isoformat()),
            )
            return [{"timestamp": r["timestamp"], "features": json.loads(r["features_json"]), "payload_sha": r["payload_sha"]} for r in cur.fetchall()]

    def build_context(self, symbol: str, *, as_of: Any) -> dict[str, Any]:
        as_of_dt = _dt(as_of)
        bars = self.get_bars(symbol, as_of=as_of_dt, timeframe="1m")
        if not bars:
            return {"symbol": symbol, "as_of": as_of_dt.isoformat(), "has_data": False}
        last_close = bars[-1]["close"]
        s_open = bars[0]["open"]

        def ret(minutes: int) -> float:
            if len(bars) <= minutes:
                ref = s_open
            else:
                ref = bars[-1 - minutes]["close"]
            return round(((last_close - ref) / ref) * 10000.0, 4) if ref else 0.0

        return {
            "symbol": symbol,
            "as_of": as_of_dt.isoformat(),
            "has_data": True,
            "last_price": last_close,
            "session_open": s_open,
            "ret_1m_bps": ret(1),
            "ret_5m_bps": ret(5),
            "ret_15m_bps": ret(15),
            "ret_open_bps": round(((last_close - s_open) / s_open) * 10000.0, 4) if s_open else 0.0,
            "bars_count": len(bars),
        }

    def verify_integrity(self, session_date: str, symbols: Iterable[str] | None = None) -> dict[str, Any]:
        with self._lock, self._conn() as conn:
            cur = conn.execute("SELECT DISTINCT symbol FROM completed_bars_1m WHERE timestamp >= ? AND timestamp <= ?;", (_open(session_date).isoformat(), _close(session_date).isoformat()))
            available = [r["symbol"] for r in cur.fetchall()]
        check_symbols = list(symbols) if symbols else available
        anomalies: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for sym in check_symbols:
            bars = self._load(session_date, sym)
            counts[sym] = len(bars)
            if not bars:
                anomalies.append({"symbol": sym, "error": "no_bars_for_session"})
                continue
            for idx in range(1, len(bars)):
                prev_t = _dt(bars[idx - 1]["timestamp"])
                curr_t = _dt(bars[idx]["timestamp"])
                gap = int((curr_t - prev_t).total_seconds())
                if gap != 60:
                    anomalies.append({"symbol": sym, "error": "timestamp_gap_or_ordering", "expected_seconds": 60, "actual_seconds": gap, "at": curr_t.isoformat()})
        return {"session_date": session_date, "symbols": check_symbols, "bar_counts": counts, "anomaly_count": len(anomalies), "anomalies": anomalies, "valid": len(anomalies) == 0}

    def seal_session(self, session_date: str, symbols: Iterable[str]) -> dict[str, Any]:
        integ = self.verify_integrity(session_date, symbols)
        if not integ["valid"]:
            raise SessionMemoryError(f"cannot_seal_invalid_session:{integ}")
        hashes = {}
        for sym in symbols:
            bars = self._load(session_date, sym)
            hashes[sym] = _sha(bars)
        manifest = {"session_date": session_date, "symbols": sorted(list(symbols)), "symbol_hashes": hashes, "bar_counts": integ["bar_counts"], "sealed_at": datetime.now(timezone.utc).isoformat()}
        manifest_sha = _sha(manifest)
        with self._lock, self._conn() as conn:
            conn.execute("INSERT INTO session_seals (session_date, payload_json, payload_sha, sealed_at) VALUES (?, ?, ?, ?) ON CONFLICT(session_date) DO UPDATE SET payload_json=excluded.payload_json, payload_sha=excluded.payload_sha, sealed_at=excluded.sealed_at;", (session_date, _json(manifest), manifest_sha, manifest["sealed_at"]))
        target = self.report_root / f"session_seal_{session_date}.json"
        target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return {"session_date": session_date, "payload_sha": manifest_sha, "artifact": str(target)}

    def verify_seal(self, session_date: str) -> dict[str, Any]:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT payload_json, payload_sha FROM session_seals WHERE session_date = ?;", (session_date,)).fetchone()
            if not row:
                return {"session_date": session_date, "sealed": False, "error": "seal_not_found"}
            manifest = json.loads(row["payload_json"])
            expected_sha = row["payload_sha"]
        if _sha(manifest) != expected_sha:
            return {"session_date": session_date, "sealed": False, "error": "seal_hash_mismatch"}
        for sym, exp_hash in manifest.get("symbol_hashes", {}).items():
            bars = self._load(session_date, sym)
            if _sha(bars) != exp_hash:
                return {"session_date": session_date, "sealed": False, "error": f"symbol_hash_mismatch:{sym}"}
        return {"session_date": session_date, "sealed": True, "payload_sha": expected_sha, "manifest": manifest}
