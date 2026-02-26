"""Utilities for reject-shadow outcome scoring.

Migration note:
- Adds deterministic horizon outcome scoring for blocked candidates.
- Adds SQLite table management for `shadow_outcomes`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Callable

from config import config as cfg
from core.time_utils import now_utc_epoch


def _safe_float(value):
    try:
        out = float(value)
    except Exception:
        return None
    if out != out:  # NaN
        return None
    return out


def normalize_horizons(horizons: list[int] | tuple[int, ...] | None = None) -> list[int]:
    out: list[int] = []
    raw = list(horizons or getattr(cfg, "SHADOW_EVAL_HORIZONS_SEC", [300, 900, 1800]) or [])
    for item in raw:
        try:
            val = int(item)
        except Exception:
            continue
        if val > 0:
            out.append(val)
    if not out:
        out = [300, 900, 1800]
    return sorted(set(out))


def _direction_mult(entry: float, stop: float | None, target: float | None, direction: str | None) -> int:
    d = str(direction or "").upper()
    if d.startswith("SELL"):
        return -1
    if target is not None and entry is not None:
        if float(target) < float(entry):
            return -1
    if stop is not None and entry is not None and target is None:
        if float(stop) > float(entry):
            return -1
    return 1


def _hit_target(price: float, target: float | None, direction_mult: int) -> bool:
    if target is None:
        return False
    if direction_mult >= 0:
        return price >= float(target)
    return price <= float(target)


def _hit_stop(price: float, stop: float | None, direction_mult: int) -> bool:
    if stop is None:
        return False
    if direction_mult >= 0:
        return price <= float(stop)
    return price >= float(stop)


def evaluate_shadow_candidate(
    *,
    entry: float,
    stop: float | None,
    target: float | None,
    direction: str | None,
    start_ts_epoch: float,
    price_points: list[tuple[float, float]],
    horizons_sec: list[int] | None = None,
) -> dict:
    """
    Evaluate target/stop outcomes over multiple horizons.
    `price_points` must be sorted tuples of (timestamp_epoch, price).
    """
    horizons = normalize_horizons(horizons_sec)
    direction_mult = _direction_mult(entry, stop, target, direction)
    outcomes: dict[int, str] = {}

    for horizon in horizons:
        cutoff = float(start_ts_epoch) + float(horizon)
        first_hit = "timeout"
        for ts_epoch, price in price_points:
            if ts_epoch < float(start_ts_epoch):
                continue
            if ts_epoch > cutoff:
                break
            if _hit_target(float(price), target, direction_mult):
                first_hit = "target"
                break
            if _hit_stop(float(price), stop, direction_mult):
                first_hit = "stop"
                break
        outcomes[int(horizon)] = first_hit

    horizon_15 = min(horizons, key=lambda val: abs(val - 900))
    cutoff_15 = float(start_ts_epoch) + float(horizon_15)
    pnl_points: list[float] = []
    last_pnl = None
    for ts_epoch, price in price_points:
        if ts_epoch < float(start_ts_epoch):
            continue
        if ts_epoch > cutoff_15:
            break
        pnl = (float(price) - float(entry)) * float(direction_mult)
        pnl_points.append(pnl)
        last_pnl = pnl

    mfe_15m = max(pnl_points) if pnl_points else None
    mae_15m = min(pnl_points) if pnl_points else None
    pnl_15m = last_pnl

    return {
        "horizons": horizons,
        "outcomes": outcomes,
        "mfe_15m": mfe_15m,
        "mae_15m": mae_15m,
        "pnl_15m": pnl_15m,
    }


def ensure_shadow_outcomes_table(conn: sqlite3.Connection, table_name: str | None = None) -> str:
    table = str(table_name or getattr(cfg, "SHADOW_OUTCOMES_TABLE", "shadow_outcomes")).strip() or "shadow_outcomes"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            candidate_id TEXT PRIMARY KEY,
            timestamp_epoch REAL,
            symbol TEXT,
            reason_code TEXT,
            direction TEXT,
            contract TEXT,
            entry REAL,
            stop REAL,
            target REAL,
            outcome_5m TEXT,
            outcome_15m TEXT,
            outcome_30m TEXT,
            mfe_15m REAL,
            mae_15m REAL,
            pnl_15m REAL,
            eval_ts_epoch REAL
        )
        """
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table}_reason_eval ON {table}(reason_code, eval_ts_epoch)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table}_symbol_ts ON {table}(symbol, timestamp_epoch)"
    )
    return table


def upsert_shadow_outcome(
    conn: sqlite3.Connection,
    row: dict,
    *,
    table_name: str | None = None,
) -> None:
    table = ensure_shadow_outcomes_table(conn, table_name=table_name)
    conn.execute(
        f"""
        INSERT INTO {table} (
            candidate_id, timestamp_epoch, symbol, reason_code, direction, contract,
            entry, stop, target, outcome_5m, outcome_15m, outcome_30m,
            mfe_15m, mae_15m, pnl_15m, eval_ts_epoch
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(candidate_id) DO UPDATE SET
            timestamp_epoch=excluded.timestamp_epoch,
            symbol=excluded.symbol,
            reason_code=excluded.reason_code,
            direction=excluded.direction,
            contract=excluded.contract,
            entry=excluded.entry,
            stop=excluded.stop,
            target=excluded.target,
            outcome_5m=excluded.outcome_5m,
            outcome_15m=excluded.outcome_15m,
            outcome_30m=excluded.outcome_30m,
            mfe_15m=excluded.mfe_15m,
            mae_15m=excluded.mae_15m,
            pnl_15m=excluded.pnl_15m,
            eval_ts_epoch=excluded.eval_ts_epoch
        """,
        (
            row.get("candidate_id"),
            row.get("timestamp_epoch"),
            row.get("symbol"),
            row.get("reason_code"),
            row.get("direction"),
            row.get("contract"),
            row.get("entry"),
            row.get("stop"),
            row.get("target"),
            row.get("outcome_5m"),
            row.get("outcome_15m"),
            row.get("outcome_30m"),
            row.get("mfe_15m"),
            row.get("mae_15m"),
            row.get("pnl_15m"),
            row.get("eval_ts_epoch"),
        ),
    )


@dataclass(frozen=True)
class ShadowCandidate:
    candidate_id: str
    timestamp_epoch: float
    symbol: str
    reason_code: str
    direction: str | None
    entry: float
    stop: float | None
    target: float | None
    contract: str | None
    instrument_token: int | None
    horizons_sec: list[int]


def parse_shadow_candidate(record: dict, *, default_horizons: list[int] | None = None) -> ShadowCandidate | None:
    if not isinstance(record, dict):
        return None
    symbol = str(record.get("symbol") or "").strip().upper()
    if not symbol:
        return None
    ts_epoch = _safe_float(record.get("timestamp_epoch"))
    if ts_epoch is None:
        ts_epoch = _safe_float(record.get("ts_epoch"))
    if ts_epoch is None:
        ts_raw = record.get("timestamp") or record.get("ts_ist")
        try:
            ts_epoch = datetime.fromisoformat(str(ts_raw)).timestamp()
        except Exception:
            ts_epoch = None
    if ts_epoch is None:
        return None
    entry = _safe_float(record.get("entry"))
    if entry is None:
        entry = _safe_float(record.get("option_ltp"))
    if entry is None:
        entry = _safe_float(record.get("ltp"))
    if entry is None:
        return None
    stop = _safe_float(record.get("stop"))
    target = _safe_float(record.get("target"))
    direction = str(record.get("direction") or "").strip().upper() or None
    reason_codes = record.get("reason_codes")
    reason_code = ""
    if isinstance(reason_codes, (list, tuple)):
        for item in reason_codes:
            text = str(item or "").strip()
            if text:
                reason_code = text
                break
    if not reason_code:
        reason_code = str(record.get("reason_code") or record.get("reason") or "unknown").strip() or "unknown"
    candidate_id = str(
        record.get("candidate_id")
        or record.get("blocked_id")
        or record.get("trade_id")
        or f"blk_{symbol}_{int(ts_epoch)}_{reason_code}"
    )
    token = record.get("instrument_token")
    try:
        instrument_token = int(token) if token is not None else None
    except Exception:
        instrument_token = None
    raw_horizons = record.get("horizon_sec") or record.get("horizons_sec") or default_horizons
    if isinstance(raw_horizons, int):
        raw_horizons = [raw_horizons]
    horizons = normalize_horizons(raw_horizons if isinstance(raw_horizons, (list, tuple)) else default_horizons)
    return ShadowCandidate(
        candidate_id=candidate_id,
        timestamp_epoch=float(ts_epoch),
        symbol=symbol,
        reason_code=reason_code,
        direction=direction,
        entry=float(entry),
        stop=stop,
        target=target,
        contract=(str(record.get("instrument_id") or record.get("contract") or "").strip() or None),
        instrument_token=instrument_token,
        horizons_sec=horizons,
    )


def load_ticks_price_points(
    conn: sqlite3.Connection,
    *,
    instrument_token: int,
    start_ts_epoch: float,
    end_ts_epoch: float,
) -> list[tuple[float, float]]:
    try:
        rows = conn.execute(
            """
            SELECT timestamp_epoch, last_price
            FROM ticks
            WHERE instrument_token = ?
              AND timestamp_epoch IS NOT NULL
              AND timestamp_epoch >= ?
              AND timestamp_epoch <= ?
              AND last_price IS NOT NULL
            ORDER BY timestamp_epoch ASC
            """,
            (int(instrument_token), float(start_ts_epoch), float(end_ts_epoch)),
        ).fetchall()
    except sqlite3.OperationalError:
        # Graceful degradation for DBs without tick history (fresh install/fallback DB).
        return []
    points: list[tuple[float, float]] = []
    for ts_epoch, price in rows:
        ts_val = _safe_float(ts_epoch)
        px_val = _safe_float(price)
        if ts_val is None or px_val is None:
            continue
        points.append((float(ts_val), float(px_val)))
    return points


def default_historical_provider(
    *,
    symbol: str,
    instrument_token: int | None,
    start_ts_epoch: float,
    end_ts_epoch: float,
    interval: str = "minute",
) -> list[tuple[float, float]]:
    if not instrument_token:
        return []
    try:
        from core.kite_client import kite_client
    except Exception:
        return []
    try:
        start_dt = datetime.fromtimestamp(float(start_ts_epoch), tz=timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30)))
        end_dt = datetime.fromtimestamp(float(end_ts_epoch), tz=timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30)))
        candles = kite_client.historical_data(int(instrument_token), start_dt, end_dt, interval=interval) or []
    except Exception:
        return []
    points: list[tuple[float, float]] = []
    for row in candles:
        if not isinstance(row, dict):
            continue
        ts = row.get("date") or row.get("ts")
        close = _safe_float(row.get("close"))
        if close is None or not hasattr(ts, "timestamp"):
            continue
        points.append((float(ts.timestamp()), float(close)))
    points.sort(key=lambda item: item[0])
    return points


def build_shadow_row(candidate: ShadowCandidate, evaluation: dict) -> dict:
    outcomes = evaluation.get("outcomes") or {}
    eval_ts = float(now_utc_epoch())
    return {
        "candidate_id": candidate.candidate_id,
        "timestamp_epoch": float(candidate.timestamp_epoch),
        "symbol": candidate.symbol,
        "reason_code": candidate.reason_code,
        "direction": candidate.direction,
        "contract": candidate.contract,
        "entry": float(candidate.entry),
        "stop": candidate.stop,
        "target": candidate.target,
        "outcome_5m": outcomes.get(300) or outcomes.get(60 * 5) or "timeout",
        "outcome_15m": outcomes.get(900) or outcomes.get(60 * 15) or "timeout",
        "outcome_30m": outcomes.get(1800) or outcomes.get(60 * 30) or "timeout",
        "mfe_15m": evaluation.get("mfe_15m"),
        "mae_15m": evaluation.get("mae_15m"),
        "pnl_15m": evaluation.get("pnl_15m"),
        "eval_ts_epoch": eval_ts,
    }
