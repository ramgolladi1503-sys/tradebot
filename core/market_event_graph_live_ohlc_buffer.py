"""Isolated OHLC buffer for market-event graph live-source observation.

This module is read-only with respect to trading decisions. It owns a separate
``OhlcBuffer`` instance so enabling live-source evidence cannot change the
production market-data OHLC state used by strategies, risk, or execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from config import config as cfg
from core.ohlc_buffer import OhlcBuffer
from core.time_utils import IST_TZ

shadow_ohlc_buffer = OhlcBuffer()
_LAST_SOURCE_TICK_EPOCH_BY_TOKEN: dict[int, float] = {}


def reset_live_source_shadow_buffer() -> None:
    shadow_ohlc_buffer._bars.clear()
    _LAST_SOURCE_TICK_EPOCH_BY_TOKEN.clear()


def record_live_source_shadow_tick(
    *,
    symbol: str,
    instrument_token: int | None,
    price: float | int | None,
    source_tick_epoch: float | int | None,
    source_type: str,
    payload_mode: str = "",
    feed_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not bool(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)):
        return {"accepted": False, "status": "DISABLED"}
    try:
        token = int(instrument_token or 0)
        tick_epoch = float(source_tick_epoch)
        price_value = float(price)
    except Exception:
        return {"accepted": False, "status": "INVALID_SHADOW_TICK"}
    if token <= 0 or price_value <= 0:
        return {"accepted": False, "status": "INVALID_SHADOW_TICK"}
    if str(source_type).lower() not in {"live_websocket", "tick_store_live"}:
        return {"accepted": False, "status": "NON_LIVE_SOURCE"}
    last_epoch = _LAST_SOURCE_TICK_EPOCH_BY_TOKEN.get(token)
    if last_epoch is not None and tick_epoch <= float(last_epoch):
        return {"accepted": False, "status": "STALE_OR_REPEATED_TICK"}

    identity = dict(feed_identity or {})
    session_id = str(identity.get("feed_session_id") or "").strip()
    if not session_id:
        return {"accepted": False, "status": "FEED_SESSION_ID_MISSING"}
    try:
        generation_int = int(identity.get("reconnect_generation"))
    except Exception:
        return {"accepted": False, "status": "RECONNECT_GENERATION_MISSING"}

    tick_dt = datetime.fromtimestamp(tick_epoch, tz=timezone.utc).astimezone(IST_TZ)
    result = shadow_ohlc_buffer.update_tick(
        str(symbol).upper(),
        price_value,
        volume=None,
        ts=tick_dt,
        provenance={
            "source_type": str(source_type).lower(),
            "live_feed_session_id": session_id,
            "reconnect_generation": generation_int,
            "instrument_token": token,
            "payload_mode": str(payload_mode or ""),
            "historical_seed": False,
            "replay_fixture": False,
            "non_live_fallback": False,
            "recovered_synthetic": False,
        },
    )
    if bool(result.get("accepted")):
        _LAST_SOURCE_TICK_EPOCH_BY_TOKEN[token] = tick_epoch
    return result


__all__ = [
    "record_live_source_shadow_tick",
    "reset_live_source_shadow_buffer",
    "shadow_ohlc_buffer",
]
