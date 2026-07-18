from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from core.session_calendar import get_session
from core.time_utils import IST_TZ


TIMEFRAME_1M = "1m"
REGULAR_SESSION_HISTORY_ALLOWANCE = 0


class SessionBarHistoryError(ValueError):
    """Raised when bar history input cannot satisfy the causal session contract."""


def _coerce_datetime(value: Any, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        out = value
    elif isinstance(value, (int, float)):
        out = datetime.fromtimestamp(float(value), tz=IST_TZ)
    else:
        try:
            out = datetime.fromisoformat(str(value))
        except Exception as exc:  # pragma: no cover - defensive only
            raise SessionBarHistoryError(f"invalid_datetime:{field_name}") from exc
    if out.tzinfo is None:
        out = out.replace(tzinfo=IST_TZ)
    return out.astimezone(IST_TZ)


def _coerce_price(value: Any, *, field_name: str) -> float:
    try:
        out = float(value)
    except Exception as exc:
        raise SessionBarHistoryError(f"invalid_price:{field_name}") from exc
    if not math.isfinite(out) or out <= 0.0:
        raise SessionBarHistoryError(f"invalid_price:{field_name}")
    return float(out)


def _coerce_volume(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    if not math.isfinite(out) or out < 0.0:
        return None
    return float(out)


def _session_window(session_date: str, *, segment: str) -> tuple[datetime, datetime]:
    sess = get_session(segment)
    day = datetime.fromisoformat(str(session_date)).date()
    open_dt = datetime.combine(day, sess.open_time, tzinfo=sess.tz).astimezone(IST_TZ)
    close_dt = datetime.combine(day, sess.close_time, tzinfo=sess.tz).astimezone(IST_TZ)
    return open_dt, close_dt


def session_history_bound(*, segment: str, timeframe: str = TIMEFRAME_1M) -> int:
    normalized_timeframe = str(timeframe or "").strip().lower()
    if normalized_timeframe != TIMEFRAME_1M:
        raise SessionBarHistoryError(f"unsupported_timeframe:{normalized_timeframe}")
    open_dt, close_dt = _session_window("2026-01-01", segment=segment)
    session_minutes = int((close_dt - open_dt).total_seconds() / 60.0)
    if session_minutes <= 0:
        raise SessionBarHistoryError("invalid_session_minutes")
    return int(session_minutes + REGULAR_SESSION_HISTORY_ALLOWANCE)


def calculate_session_range_width_pct(
    *,
    day_high: Any,
    day_low: Any,
    reference_price: Any,
) -> float | None:
    try:
        high = _coerce_price(day_high, field_name="day_high")
        low = _coerce_price(day_low, field_name="day_low")
        denominator = _coerce_price(reference_price, field_name="reference_price")
    except SessionBarHistoryError:
        return None
    if high < low or denominator <= 0.0:
        return None
    return float((high - low) / denominator)


def calculate_session_range_width_pct_from_completed_history(
    *,
    symbol: str,
    bars: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    cutoff_timestamp: Any,
    segment: str,
    reference_price: Any,
    timeframe: str = TIMEFRAME_1M,
) -> float | None:
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        return None

    try:
        normalized_cutoff = _coerce_datetime(cutoff_timestamp, field_name="cutoff_timestamp")
    except SessionBarHistoryError:
        return None

    session_date = normalized_cutoff.date().isoformat()
    open_dt, close_dt = _session_window(session_date, segment=segment)

    day_high: float | None = None
    day_low: float | None = None
    seen_starts: set[datetime] = set()
    previous_start: datetime | None = None

    for raw_bar in list(bars or []):
        raw_symbol = str(raw_bar.get("symbol") or raw_bar.get("instrument") or "").strip().upper()
        if raw_symbol and raw_symbol != normalized_symbol:
            return None
        raw_session_date = str(raw_bar.get("session_date") or "").strip()
        if raw_session_date and raw_session_date != session_date:
            return None

        bar_start_raw = raw_bar.get("ts", raw_bar.get("date", raw_bar.get("bar_start_timestamp")))
        if bar_start_raw is None:
            return None
        try:
            bar_start = _coerce_datetime(bar_start_raw, field_name="bar_timestamp")
        except SessionBarHistoryError:
            return None
        if bar_start.second != 0 or bar_start.microsecond != 0:
            return None
        bar_start = bar_start.replace(second=0, microsecond=0)
        if bar_start < open_dt or bar_start >= close_dt:
            continue
        if bar_start.date().isoformat() != session_date:
            continue
        if previous_start is not None and bar_start < previous_start:
            return None
        if bar_start in seen_starts:
            return None
        previous_start = bar_start
        seen_starts.add(bar_start)

        bar_end_raw = raw_bar.get("bar_end_timestamp")
        if bar_end_raw is not None:
            try:
                bar_end = _coerce_datetime(bar_end_raw, field_name="bar_end_timestamp")
            except SessionBarHistoryError:
                return None
            if bar_end - bar_start != timedelta(minutes=1):
                return None
        else:
            bar_end = bar_start + timedelta(minutes=1)
        if bar_end > normalized_cutoff:
            continue

        try:
            open_price = _coerce_price(raw_bar.get("open"), field_name="open")
            high_price = _coerce_price(raw_bar.get("high"), field_name="high")
            low_price = _coerce_price(raw_bar.get("low"), field_name="low")
            close_price = _coerce_price(raw_bar.get("close"), field_name="close")
        except SessionBarHistoryError:
            return None
        if high_price < max(open_price, close_price, low_price):
            return None
        if low_price > min(open_price, close_price, high_price):
            return None

        day_high = high_price if day_high is None else max(day_high, high_price)
        day_low = low_price if day_low is None else min(day_low, low_price)

    if day_high is None or day_low is None:
        return None
    return calculate_session_range_width_pct(
        day_high=day_high,
        day_low=day_low,
        reference_price=reference_price,
    )


@dataclass(frozen=True)
class CompletedBarSnapshot:
    symbol: str
    session_date: str
    timeframe: str
    bar_start_timestamp: str
    bar_end_timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    source: str
    source_timestamp: str
    receipt_timestamp: str | None
    is_complete: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "session_date": self.session_date,
            "timeframe": self.timeframe,
            "bar_start_timestamp": self.bar_start_timestamp,
            "bar_end_timestamp": self.bar_end_timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "source": self.source,
            "source_timestamp": self.source_timestamp,
            "receipt_timestamp": self.receipt_timestamp,
            "is_complete": self.is_complete,
        }


@dataclass(frozen=True)
class SessionBarHistoryState:
    symbol: str
    session_date: str
    timeframe: str
    source: str
    partial_session: bool
    is_complete: bool
    history_bound: int
    completed_bar_count: int
    latest_completed_timestamp: str | None
    open_price: float | None
    day_high: float | None
    day_low: float | None
    previous_completed_close: float | None
    history_hash: str
    completed_bar_history: tuple[CompletedBarSnapshot, ...]

    def history_payload(self) -> list[dict[str, Any]]:
        return [bar.to_dict() for bar in self.completed_bar_history]

    def provenance_payload(self, *, source_component: str, receipt_timestamp: str | None = None) -> dict[str, Any]:
        payload = {
            "status": "TRUTHFUL" if self.completed_bar_history else "INCOMPLETE",
            "source_component": str(source_component or "").strip() or "core.session_bar_history",
            "source_field": "completed_bar_history",
            "source": self.source,
            "symbol": self.symbol,
            "session_date": self.session_date,
            "timeframe": self.timeframe,
            "completed_bar_count": self.completed_bar_count,
            "latest_completed_timestamp": self.latest_completed_timestamp,
            "history_bound": self.history_bound,
            "history_hash": self.history_hash,
            "partial_session": self.partial_session,
            "is_complete": self.is_complete,
            "source_event_timestamp": self.latest_completed_timestamp,
            "receipt_timestamp": receipt_timestamp or self.latest_completed_timestamp,
            "scope": "session_completed_bar_history",
            "complete": self.is_complete,
        }
        return payload


def build_session_bar_history_state(
    *,
    symbol: str,
    bars: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    cutoff_timestamp: Any,
    segment: str,
    source: str,
    timeframe: str = TIMEFRAME_1M,
    partial_session: bool | None = None,
    receipt_timestamp: Any | None = None,
) -> SessionBarHistoryState:
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        raise SessionBarHistoryError("symbol_required")

    normalized_cutoff = _coerce_datetime(cutoff_timestamp, field_name="cutoff_timestamp")
    session_date = normalized_cutoff.date().isoformat()
    open_dt, close_dt = _session_window(session_date, segment=segment)
    bound = session_history_bound(segment=segment, timeframe=timeframe)
    normalized_receipt = (
        _coerce_datetime(receipt_timestamp, field_name="receipt_timestamp").isoformat()
        if receipt_timestamp is not None
        else None
    )

    completed: list[CompletedBarSnapshot] = []
    seen_starts: set[datetime] = set()
    previous_start: datetime | None = None
    volume_truthful = False

    for raw_bar in list(bars or []):
        bar_start_raw = raw_bar.get("ts", raw_bar.get("date", raw_bar.get("bar_start_timestamp")))
        if bar_start_raw is None:
            raise SessionBarHistoryError("missing_bar_timestamp")
        bar_start = _coerce_datetime(bar_start_raw, field_name="bar_timestamp")
        bar_start = bar_start.replace(second=0, microsecond=0)
        if bar_start < open_dt or bar_start >= close_dt:
            continue
        if bar_start.date().isoformat() != session_date:
            continue
        if previous_start is not None and bar_start < previous_start:
            raise SessionBarHistoryError("out_of_order_bar")
        if bar_start in seen_starts:
            raise SessionBarHistoryError("duplicate_bar_timestamp")
        previous_start = bar_start
        seen_starts.add(bar_start)

        bar_end_raw = raw_bar.get("bar_end_timestamp")
        if bar_end_raw is not None:
            bar_end = _coerce_datetime(bar_end_raw, field_name="bar_end_timestamp")
        else:
            bar_end = bar_start + timedelta(minutes=1)
        if bar_end > normalized_cutoff:
            continue

        open_price = _coerce_price(raw_bar.get("open"), field_name="open")
        high_price = _coerce_price(raw_bar.get("high"), field_name="high")
        low_price = _coerce_price(raw_bar.get("low"), field_name="low")
        close_price = _coerce_price(raw_bar.get("close"), field_name="close")
        if high_price < max(open_price, close_price, low_price):
            raise SessionBarHistoryError("invalid_ohlc_high")
        if low_price > min(open_price, close_price, high_price):
            raise SessionBarHistoryError("invalid_ohlc_low")

        volume = _coerce_volume(raw_bar.get("volume"))
        if volume is not None and volume > 0.0:
            volume_truthful = True

        completed.append(
            CompletedBarSnapshot(
                symbol=normalized_symbol,
                session_date=session_date,
                timeframe=timeframe,
                bar_start_timestamp=bar_start.isoformat(),
                bar_end_timestamp=bar_end.isoformat(),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
                source=str(source or "").strip() or "unknown",
                source_timestamp=bar_end.isoformat(),
                receipt_timestamp=normalized_receipt,
                is_complete=True,
            )
        )

    if not volume_truthful:
        completed = [
            CompletedBarSnapshot(
                symbol=bar.symbol,
                session_date=bar.session_date,
                timeframe=bar.timeframe,
                bar_start_timestamp=bar.bar_start_timestamp,
                bar_end_timestamp=bar.bar_end_timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=None,
                source=bar.source,
                source_timestamp=bar.source_timestamp,
                receipt_timestamp=bar.receipt_timestamp,
                is_complete=bar.is_complete,
            )
            for bar in completed
        ]

    if len(completed) > bound:
        raise SessionBarHistoryError("history_bound_exceeded")

    completed_tuple = tuple(completed)
    latest_completed_timestamp = completed_tuple[-1].bar_end_timestamp if completed_tuple else None
    computed_partial = bool(
        partial_session
        if partial_session is not None
        else (
            (not completed_tuple)
            or len(completed_tuple) < bound
            or latest_completed_timestamp != close_dt.isoformat()
        )
    )
    is_complete = bool((not computed_partial) and len(completed_tuple) == bound)
    open_price = completed_tuple[0].open if completed_tuple else None
    day_high = max((bar.high for bar in completed_tuple), default=None)
    day_low = min((bar.low for bar in completed_tuple), default=None)
    previous_completed_close = completed_tuple[-2].close if len(completed_tuple) >= 2 else None
    history_payload = [bar.to_dict() for bar in completed_tuple]
    history_hash = hashlib.sha256(
        json.dumps(history_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()

    return SessionBarHistoryState(
        symbol=normalized_symbol,
        session_date=session_date,
        timeframe=timeframe,
        source=str(source or "").strip() or "unknown",
        partial_session=bool(computed_partial),
        is_complete=bool(is_complete),
        history_bound=bound,
        completed_bar_count=len(completed_tuple),
        latest_completed_timestamp=latest_completed_timestamp,
        open_price=open_price,
        day_high=day_high,
        day_low=day_low,
        previous_completed_close=previous_completed_close,
        history_hash=history_hash,
        completed_bar_history=completed_tuple,
    )
