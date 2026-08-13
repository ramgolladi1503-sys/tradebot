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
_ACTIVE_CAPTURE_IDENTITY: dict[str, Any] | None = None


def reset_live_source_shadow_buffer() -> None:
    shadow_ohlc_buffer._bars.clear()
    _LAST_SOURCE_TICK_EPOCH_BY_TOKEN.clear()
    global _ACTIVE_CAPTURE_IDENTITY
    _ACTIVE_CAPTURE_IDENTITY = None


def _capture_identity_from(feed_identity: Mapping[str, Any] | None, *, provider: str, token_domain: str, universe_hash: str) -> dict[str, Any]:
    identity = {
        "provider": provider,
        "token_domain": token_domain,
        "universe_hash": universe_hash,
        "feed_session_id": str((feed_identity or {}).get("feed_session_id") or "").strip(),
        "feed_epoch": int((feed_identity or {}).get("feed_epoch") or 0),
        "reconnect_generation": int((feed_identity or {}).get("reconnect_generation") or 0),
    }
    return identity


def _identity_changed(identity: Mapping[str, Any]) -> bool:
    current = dict(_ACTIVE_CAPTURE_IDENTITY or {})
    return any(current.get(key) != identity.get(key) for key in ("provider", "token_domain", "universe_hash", "feed_session_id", "feed_epoch"))


def _apply_identity(identity: Mapping[str, Any]) -> None:
    global _ACTIVE_CAPTURE_IDENTITY
    if _identity_changed(identity):
        reset_live_source_shadow_buffer()
        _ACTIVE_CAPTURE_IDENTITY = dict(identity)


def record_live_source_shadow_tick(
    *,
    symbol: str,
    instrument_token: int | None,
    price: float | int | None,
    source_tick_epoch: float | int | None,
    source_type: str,
    payload_mode: str = "",
    feed_identity: Mapping[str, Any] | None = None,
    provider: str = "kite",
    token_domain: str = "kite_instrument_token",
    universe_hash: str = "",
    packet_kind: str = "",
    is_full_payload: bool = False,
) -> dict[str, Any]:
    if not bool(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)):
        return {"accepted": False, "status": "DISABLED"}
    try:
        token = int(instrument_token or 0)
        price_value = float(price)
    except Exception:
        return {"accepted": False, "status": "INVALID_SHADOW_TICK"}
    if token <= 0 or price_value <= 0:
        return {"accepted": False, "status": "INVALID_SHADOW_TICK"}
    normalized_source_type = str(source_type).lower().strip()
    if normalized_source_type not in {"live_websocket", "deterministic_test"}:
        return {"accepted": False, "status": "NON_LIVE_SOURCE"}
    if str(provider).strip().lower() != "kite" or str(token_domain).strip() != "kite_instrument_token":
        return {"accepted": False, "status": "CAPTURE_IDENTITY_INVALID"}
    if not str(universe_hash).strip() or not str(symbol).strip():
        return {"accepted": False, "status": "CAPTURE_IDENTITY_INVALID"}
    identity = dict(feed_identity or {})
    session_id = str(identity.get("feed_session_id") or "").strip()
    if not session_id:
        return {"accepted": False, "status": "FEED_SESSION_ID_MISSING"}
    try:
        generation_int = int(identity.get("reconnect_generation"))
    except Exception:
        return {"accepted": False, "status": "RECONNECT_GENERATION_MISSING"}
    capture_identity = _capture_identity_from(identity, provider=provider, token_domain=token_domain, universe_hash=universe_hash)
    _apply_identity(capture_identity)
    if source_tick_epoch is None:
        return {
            "accepted": False,
            "delivery_observed": True,
            "bar_written": False,
            "status": "DELIVERED_NO_SOURCE_TIMESTAMP",
            "capture_identity": capture_identity,
            "packet_kind": packet_kind,
            "is_full_payload": bool(is_full_payload),
        }
    try:
        tick_epoch = float(source_tick_epoch)
    except Exception:
        return {"accepted": False, "status": "INVALID_SHADOW_TICK"}
    last_epoch = _LAST_SOURCE_TICK_EPOCH_BY_TOKEN.get(token)
    if last_epoch is not None and tick_epoch <= float(last_epoch):
        return {"accepted": False, "status": "STALE_OR_REPEATED_TICK", "capture_identity": capture_identity}

    tick_dt = datetime.fromtimestamp(tick_epoch, tz=timezone.utc).astimezone(IST_TZ)
    offline_fixture = normalized_source_type == "deterministic_test"
    result = shadow_ohlc_buffer.update_tick(
        str(symbol).upper(),
        price_value,
        volume=None,
        ts=tick_dt,
        provenance={
            "source_type": normalized_source_type,
            "symbol": str(symbol).upper(),
            "live_feed_session_id": session_id,
            "feed_epoch": int(capture_identity.get("feed_epoch") or 0),
            "reconnect_generation": generation_int,
            "instrument_token": token,
            "payload_mode": str(payload_mode or ""),
            "packet_kind": str(packet_kind or ""),
            "provider": provider,
            "token_domain": token_domain,
            "universe_hash": universe_hash,
            "historical_seed": False,
            "replay_fixture": offline_fixture,
            "fixture_kind": "OFFLINE_DETERMINISTIC_TEST" if offline_fixture else None,
            "live_evidence": not offline_fixture,
            "non_live_fallback": False,
            "recovered_synthetic": False,
        },
    )
    if bool(result.get("accepted")):
        _LAST_SOURCE_TICK_EPOCH_BY_TOKEN[token] = tick_epoch
    result["capture_identity"] = capture_identity
    result["delivery_observed"] = True
    result["bar_written"] = bool(result.get("accepted"))
    result["packet_kind"] = str(packet_kind or "")
    result["is_full_payload"] = bool(is_full_payload)
    result["live_evidence"] = not offline_fixture
    result["replay_fixture"] = offline_fixture
    if offline_fixture:
        result["fixture_kind"] = "OFFLINE_DETERMINISTIC_TEST"
    return result


__all__ = [
    "record_live_source_shadow_tick",
    "reset_live_source_shadow_buffer",
    "shadow_ohlc_buffer",
]
