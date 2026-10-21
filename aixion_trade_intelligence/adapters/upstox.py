from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from ..contracts import CanonicalEvent, parse_timestamp


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and result not in (float("inf"), float("-inf")) else None


def _timestamp_from_epoch(value: Any) -> datetime | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    # Unit is derived from magnitude rather than a provider-specific hardcode.
    absolute = abs(number)
    if absolute >= 1e17:
        seconds = number / 1e9
    elif absolute >= 1e14:
        seconds = number / 1e6
    elif absolute >= 1e11:
        seconds = number / 1e3
    else:
        seconds = number
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _first_timestamp(row: Mapping[str, Any], *keys: str) -> datetime | None:
    for key in keys:
        value = row.get(key)
        if value in (None, "", 0, "0"):
            continue
        if isinstance(value, str):
            try:
                return parse_timestamp(value, field_name=key)
            except Exception:
                pass
        parsed = _timestamp_from_epoch(value)
        if parsed is not None:
            return parsed
    return None


def adapt_upstox_quote_row(
    row: Mapping[str, Any],
    *,
    session_id: str,
    producer_sequence: int,
    observed_at: datetime | None = None,
) -> CanonicalEvent | None:
    instrument = _text(row.get("instrument_key"))
    if not instrument or instrument == "marketInfo":
        return None
    receive_time = _first_timestamp(row, "receive_wall_ts_utc", "receive_time") or observed_at
    event_time = _first_timestamp(
        row,
        "source_exchange_ts",
        "provider_last_trade_ts",
        "provider_current_ts",
        "ts",
    )
    if event_time is None:
        event_time = receive_time
    if receive_time is None:
        receive_time = event_time or datetime.now(timezone.utc)
    if event_time is None:
        event_time = receive_time
    available_time = max(event_time, receive_time)
    bid = _number(row.get("bid_price_1") if "bid_price_1" in row else row.get("bid_price"))
    ask = _number(row.get("ask_price_1") if "ask_price_1" in row else row.get("ask_price"))
    ltp = _number(row.get("ltp"))
    payload: dict[str, Any] = {
        "ltp": ltp,
        "bid": bid,
        "ask": ask,
        "volume": _number(row.get("volume")),
        "oi": _number(row.get("open_interest") if "open_interest" in row else row.get("oi")),
        "iv": _number(row.get("implied_volatility") if "implied_volatility" in row else row.get("iv")),
        "delta": _number(row.get("delta")),
        "gamma": _number(row.get("gamma")),
        "theta": _number(row.get("theta")),
        "vega": _number(row.get("vega")),
        "depth_available": bid is not None and ask is not None,
        "source_schema_version": _text(row.get("schema_version")),
        "source_capture_run_id": _text(row.get("capture_run_id")),
        "source_local_sequence": row.get("local_sequence"),
    }
    return CanonicalEvent(
        event_type="MARKET_QUOTE",
        session_id=session_id,
        run_id=_text(row.get("capture_run_id")) or session_id,
        trace_id=session_id,
        producer_id="upstox-market-data",
        producer_sequence=producer_sequence,
        source_component="upstox_capture",
        source_provider=_text(row.get("provider")) or "UPSTOX",
        event_time=event_time,
        source_time=event_time,
        receive_time=receive_time,
        available_time=available_time,
        parse_time=available_time,
        persist_time=available_time,
        instrument_key=instrument,
        underlying=_text(row.get("underlying_symbol")),
        data_quality_state=("TWO_SIDED_QUOTE" if bid is not None and ask is not None else "LTP_ONLY"),
        authority_class="UPSTOX_CAPTURE_OBSERVED",
        payload=payload,
    )
