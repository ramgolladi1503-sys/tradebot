from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import math
import sqlite3


IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")


class CasA1TickPointError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TickPoint:
    instrument_key: str
    label: str
    price: float
    available_time: str
    source_event_id: str
    source_provider: str
    source_tick_epoch: float
    lag_seconds_from_checkpoint: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _checkpoint_bounds(session_date: str, clock: str) -> tuple[float, float]:
    try:
        day = date.fromisoformat(session_date)
        hh, mm = (int(part) for part in clock.split(":", 1))
    except Exception as exc:
        raise CasA1TickPointError("invalid session date/checkpoint") from exc
    start = datetime.combine(day, time(hh, mm), tzinfo=IST)
    end = start + timedelta(minutes=1)
    return start.timestamp(), end.timestamp()


def _finite_positive(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CasA1TickPointError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise CasA1TickPointError(f"{field} must be finite and positive")
    return number


def extract_first_tick_in_checkpoint_minute(
    *,
    db_path: Path,
    instrument_token: int,
    instrument_key: str,
    session_date: str,
    checkpoint: str,
    label: str,
    source_provider: str = "KITE",
) -> TickPoint:
    if instrument_token <= 0 or not instrument_key.strip():
        raise CasA1TickPointError("exact futures token and instrument key are required")
    start, end = _checkpoint_bounds(session_date, checkpoint)
    uri = f"file:{db_path.resolve()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    except sqlite3.Error as exc:
        raise CasA1TickPointError(f"cannot open tick DB read-only: {exc}") from exc
    try:
        row = conn.execute(
            """
            SELECT timestamp_epoch, last_price, COALESCE(timestamp_iso, timestamp, '')
            FROM ticks
            WHERE instrument_token = ?
              AND timestamp_epoch >= ?
              AND timestamp_epoch < ?
            ORDER BY timestamp_epoch ASC
            LIMIT 1
            """,
            (int(instrument_token), float(start), float(end)),
        ).fetchone()
    except sqlite3.Error as exc:
        raise CasA1TickPointError(f"tick DB query failed: {exc}") from exc
    finally:
        conn.close()
    if row is None:
        raise CasA1TickPointError(
            f"no exact futures tick in checkpoint minute {session_date} {checkpoint} for token {instrument_token}"
        )
    epoch = _finite_positive(row[0], "timestamp_epoch")
    price = _finite_positive(row[1], "last_price")
    available = datetime.fromtimestamp(epoch, tz=UTC)
    if available.astimezone(IST).date().isoformat() != session_date:
        raise CasA1TickPointError("cross-session futures tick rejected")
    lag = epoch - start
    if lag < 0 or lag >= 60:
        raise CasA1TickPointError("checkpoint tick lag outside exact minute")
    event_id = f"tickdb:{instrument_token}:{epoch:.6f}"
    return TickPoint(
        instrument_key=instrument_key,
        label=label,
        price=price,
        available_time=available.isoformat().replace("+00:00", "Z"),
        source_event_id=event_id,
        source_provider=source_provider.strip().upper(),
        source_tick_epoch=epoch,
        lag_seconds_from_checkpoint=lag,
    )


def extract_frozen_futures_points(
    *,
    db_path: Path,
    futures_token: int,
    futures_instrument: str,
    session_date: str,
    source_provider: str = "KITE",
) -> dict[str, Any]:
    p1529 = extract_first_tick_in_checkpoint_minute(
        db_path=db_path,
        instrument_token=futures_token,
        instrument_key=futures_instrument,
        session_date=session_date,
        checkpoint="15:29",
        label="15:29",
        source_provider=source_provider,
    )
    p1539 = extract_first_tick_in_checkpoint_minute(
        db_path=db_path,
        instrument_token=futures_token,
        instrument_key=futures_instrument,
        session_date=session_date,
        checkpoint="15:39",
        label="15:39",
        source_provider=source_provider,
    )
    if p1539.source_tick_epoch <= p1529.source_tick_epoch:
        raise CasA1TickPointError("non-monotonic frozen futures point timestamps")
    return {
        "schema_version": 1,
        "evidence_kind": "CAS_A1_FUTURES_POINT_MARKS",
        "session_date": session_date,
        "futures_instrument": futures_instrument,
        "point_marks": [p1529.to_dict(), p1539.to_dict()],
        "read_only_tick_db": True,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
    }
