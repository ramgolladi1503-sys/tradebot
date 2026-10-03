"""Isolated OHLC buffer for market-event graph live-source observation.

This module is read-only with respect to trading decisions. It owns a separate
``OhlcBuffer`` instance so enabling live-source evidence cannot change the
production market-data OHLC state used by strategies, risk, or execution.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import time
from typing import Any, Mapping

from config import config as cfg
from core.ohlc_buffer import OhlcBuffer
from core.time_utils import IST_TZ

shadow_ohlc_buffer = OhlcBuffer()
_SESSION_STORE: Any | None = None
_SESSION_DATE: str | None = None
_SESSION_SYMBOLS: tuple[str, ...] = ("NIFTY",)
_LAST_SOURCE_TICK_EPOCH_BY_TOKEN: dict[int, float] = {}
_LAST_CUMULATIVE_VOLUME_BY_TOKEN: dict[int, tuple[str, float]] = {}
_ACTIVE_CAPTURE_IDENTITY: dict[str, Any] | None = None


def reset_live_source_shadow_buffer() -> None:
    shadow_ohlc_buffer._bars.clear()
    _LAST_SOURCE_TICK_EPOCH_BY_TOKEN.clear()
    _LAST_CUMULATIVE_VOLUME_BY_TOKEN.clear()
    global _ACTIVE_CAPTURE_IDENTITY
    _ACTIVE_CAPTURE_IDENTITY = None


def configure_live_source_session_store(
    store: Any | None, *, session_date: str | None,
    symbols: tuple[str, ...] = ("NIFTY",),
    restore_as_of: datetime | None = None,
) -> None:
    """Bind durable bars only to the isolated read-only shadow buffer."""
    global _SESSION_STORE, _SESSION_DATE, _SESSION_SYMBOLS
    if store is not None:
        if not session_date:
            raise ValueError("SESSION_DATE_REQUIRED_FOR_BAR_STORE")
        if not isinstance(restore_as_of, datetime):
            raise ValueError("BAR_STORE_RESTORE_CUTOFF_REQUIRED")
        from datetime import date

        date.fromisoformat(str(session_date))
    _SESSION_STORE = store
    _SESSION_DATE = str(session_date) if session_date is not None else None
    _SESSION_SYMBOLS = tuple(sorted({str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}))
    reset_live_source_shadow_buffer()
    if store is not None and restore_as_of is not None:
        for symbol in _SESSION_SYMBOLS:
            _restore_completed_bars(symbol, as_of=restore_as_of)


def _restore_completed_bars(symbol: str, *, as_of: datetime) -> None:
    if _SESSION_STORE is None or _SESSION_DATE is None:
        return
    if as_of.date().isoformat() != _SESSION_DATE:
        return
    bars = _SESSION_STORE.get_bars(
        symbol,
        as_of=as_of,
        timeframe="1m",
        session_date=_SESSION_DATE,
    )
    target = shadow_ohlc_buffer._bars[str(symbol).upper()]
    restored_by_ts = {bar.get("ts"): bar for bar in target if isinstance(bar.get("ts"), datetime)}
    for row in bars:
        ts = row.get("ts")
        if not isinstance(ts, datetime) or ts.date().isoformat() != _SESSION_DATE:
            raise ValueError("RESTORED_BAR_SESSION_IDENTITY_INVALID")
        if ts + timedelta(seconds=60) > as_of:
            continue
        provenance = dict(row.get("bar_provenance") or row.get("provenance") or {})
        provenance["recovered_completed_bar"] = True
        provenance["durable_persisted"] = True
        provenance["persistence_row_sha256"] = str(row.get("row_hash") or "")
        recovered = {
            "ts": ts,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": None if row.get("volume") is None else float(row["volume"]),
            "bar_provenance": provenance,
        }
        existing = restored_by_ts.get(ts)
        if existing is not None:
            fields = ("open", "high", "low", "close", "volume")
            if any(existing.get(field) != recovered.get(field) for field in fields):
                raise ValueError("RESTORED_BAR_CONFLICTS_WITH_SHADOW_BUFFER")
            continue
        restored_by_ts[ts] = recovered
    target.clear()
    target.extend(restored_by_ts[ts] for ts in sorted(restored_by_ts))


def persist_completed_live_source_shadow_bars(*, as_of: datetime, symbol: str | None = None) -> dict[str, int]:
    """Persist bars complete at the caller's event-time cutoff, then report counts."""
    if _SESSION_STORE is None or _SESSION_DATE is None:
        return {"persisted": 0, "already_durable": 0, "skipped": 0}
    if not isinstance(as_of, datetime):
        raise ValueError("BAR_PERSISTENCE_AS_OF_REQUIRED")
    cutoff = as_of.astimezone(IST_TZ) if as_of.tzinfo is not None else as_of.replace(tzinfo=IST_TZ)
    if cutoff.date().isoformat() != _SESSION_DATE:
        return {"persisted": 0, "already_durable": 0, "skipped": 0}
    symbols = (str(symbol).strip().upper(),) if symbol else _SESSION_SYMBOLS
    result = {"persisted": 0, "already_durable": 0, "skipped": 0}
    for current_symbol in symbols:
        bars = shadow_ohlc_buffer.get_bars(current_symbol)
        for bar in bars:
            ts = bar.get("ts")
            if not isinstance(ts, datetime) or ts.date().isoformat() != _SESSION_DATE:
                result["skipped"] += 1
                continue
            if ts + timedelta(seconds=60) > cutoff:
                continue
            provenance = dict(bar.get("bar_provenance") or {})
            if provenance.get("durable_persisted") is True:
                result["already_durable"] += 1
                continue
            source_type = str(provenance.get("source_type") or "").strip().lower()
            if (source_type not in {"live_websocket", "tick_store_live"}
                    or provenance.get("replay_fixture") is True
                    or provenance.get("non_live_fallback") is True
                    or provenance.get("recovered_synthetic") is True
                    or provenance.get("historical_seed") is True):
                result["skipped"] += 1
                continue
            durable_bar = dict(bar)
            durable_bar["bar_provenance"] = {**provenance, "durable_persisted": True}
            persistence_started = time.perf_counter()
            stored = _SESSION_STORE.persist_completed_bar(
                current_symbol, durable_bar, completed_as_of=cutoff
            )
            if stored.get("persisted") is not True:
                raise RuntimeError(f"COMPLETED_BAR_PERSISTENCE_FAILED:{stored.get('status')}")
            bar["bar_provenance"] = {
                **durable_bar["bar_provenance"],
                "persistence_row_sha256": str(stored.get("row_hash") or ""),
            }
            from core.candle_pipeline_diagnostics import emit_candle_pipeline_event
            emit_candle_pipeline_event(
                symbol=current_symbol, timeframe="1m", stage="T5_BAR_PERSISTED",
                source_event_ts=cutoff, bucket_start=ts,
                bucket_end=ts + timedelta(seconds=60), bar_ts=ts,
                bar_state="COMPLETED_DURABLE", bar_count=len(bars),
                feed_session_id=provenance.get("live_feed_session_id"),
                instrument_token=provenance.get("instrument_token"),
                producer="core.market_event_graph_live_ohlc_buffer",
                details={
                    "row_sha256": stored.get("row_hash"),
                    "store_status": stored.get("status"),
                    "persistence_latency_ms": (time.perf_counter() - persistence_started) * 1000.0,
                },
            )
            result["persisted"] += int(stored.get("status") == "INSERTED")
            result["already_durable"] += int(stored.get("status") == "EXISTS")
    return result


def get_live_source_shadow_completed_bars(symbol: str, *, as_of: datetime) -> list[dict[str, Any]]:
    try:
        persist_completed_live_source_shadow_bars(as_of=as_of, symbol=symbol)
        cutoff = as_of.astimezone(IST_TZ) if as_of.tzinfo is not None else as_of.replace(tzinfo=IST_TZ)
        bars = shadow_ohlc_buffer.get_completed_bars(symbol, as_of=as_of)
        return [
            bar for bar in bars
            if isinstance(bar.get("ts"), datetime)
            and (bar["ts"].astimezone(IST_TZ) if bar["ts"].tzinfo is not None else bar["ts"].replace(tzinfo=IST_TZ)).date() == cutoff.date()
        ]
    except Exception as exc:
        from core.candle_pipeline_diagnostics import emit_candle_pipeline_event
        emit_candle_pipeline_event(
            symbol=str(symbol), timeframe="1m", stage="T5_BAR_PERSISTED",
            source_event_ts=as_of, bar_state="PERSISTENCE_BLOCKED",
            producer="core.market_event_graph_live_ohlc_buffer",
            reason=f"{type(exc).__name__}:{exc}",
        )
        raise


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
    return any(current.get(key) != identity.get(key) for key in ("provider", "token_domain", "universe_hash", "feed_session_id", "feed_epoch", "reconnect_generation"))


def _apply_identity(identity: Mapping[str, Any], *, as_of: datetime) -> None:
    global _ACTIVE_CAPTURE_IDENTITY
    if _identity_changed(identity):
        # Callback-side identity changes must never query/write SQLite. Keep
        # only bars whose event-time interval has elapsed; the observer cycle
        # persists them off the WebSocket callback path.
        for bars in shadow_ohlc_buffer._bars.values():
            completed = [
                bar for bar in bars
                if isinstance(bar.get("ts"), datetime)
                and bar["ts"] + timedelta(seconds=60) <= as_of
            ]
            bars.clear()
            bars.extend(completed)
        _LAST_SOURCE_TICK_EPOCH_BY_TOKEN.clear()
        _LAST_CUMULATIVE_VOLUME_BY_TOKEN.clear()
        _ACTIVE_CAPTURE_IDENTITY = dict(identity)


def _derive_cumulative_volume_delta(
    *, token: int, cumulative_volume: Any, tick_epoch: float, feed_session_id: str
) -> tuple[float | None, bool, str, tuple[str, float] | None]:
    """Convert Kite's cumulative daily volume to an observed increment.

    Increments are attributed to the current source tick minute. When an
    observation gap spans minutes, this is an estimate, not exchange bucket
    volume. The first value, day/session reset, regression, and invalid values
    produce an explicitly incomplete volume observation.
    """
    try:
        cumulative = float(cumulative_volume)
        if not math.isfinite(cumulative) or cumulative < 0:
            raise ValueError("cumulative volume must be finite and nonnegative")
    except (TypeError, ValueError, OverflowError):
        return None, False, "MISSING_OR_INVALID_CUMULATIVE", _LAST_CUMULATIVE_VOLUME_BY_TOKEN.get(token)

    day_key = datetime.fromtimestamp(tick_epoch, tz=timezone.utc).astimezone(IST_TZ).date().isoformat()
    baseline_key = f"{feed_session_id}:{day_key}"
    previous = _LAST_CUMULATIVE_VOLUME_BY_TOKEN.get(token)
    if previous is None or previous[0] != baseline_key:
        return None, False, "BASELINE_REQUIRED", (baseline_key, cumulative)
    if cumulative < previous[1]:
        return None, False, "CUMULATIVE_REGRESSION_REBASELINE", (baseline_key, cumulative)
    return cumulative - previous[1], True, "DELTA_OBSERVED", (baseline_key, cumulative)


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
    cumulative_volume: Any = None,
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
    if _SESSION_STORE is not None and _SESSION_DATE is not None:
        if tick_dt.date().isoformat() != _SESSION_DATE:
            return {
                "accepted": False,
                "bar_written": False,
                "status": "SESSION_DATE_MISMATCH",
                "capture_identity": capture_identity,
            }
    try:
        _apply_identity(capture_identity, as_of=tick_dt)
        existing = shadow_ohlc_buffer.get_bars(str(symbol).upper())
        if (existing and existing[-1].get("ts") == tick_dt.replace(second=0, microsecond=0)
                and bool((existing[-1].get("bar_provenance") or {}).get("durable_persisted"))):
            return {
                "accepted": False,
                "bar_written": False,
                "status": "LATE_TICK_AFTER_DURABLE_FINALIZATION",
                "capture_identity": capture_identity,
            }
    except Exception as exc:
        return {
            "accepted": False,
            "bar_written": False,
            "status": f"SESSION_BAR_STORE_BLOCKED:{type(exc).__name__}:{exc}",
            "capture_identity": capture_identity,
        }
    offline_fixture = normalized_source_type == "deterministic_test"
    volume_delta, volume_complete, volume_status, next_volume_baseline = _derive_cumulative_volume_delta(
        token=token,
        cumulative_volume=cumulative_volume,
        tick_epoch=tick_epoch,
        feed_session_id=session_id,
    )
    try:
        cumulative_volume_value = float(cumulative_volume)
        if not math.isfinite(cumulative_volume_value) or cumulative_volume_value < 0:
            cumulative_volume_value = None
    except (TypeError, ValueError, OverflowError):
        cumulative_volume_value = None
    result = shadow_ohlc_buffer.update_tick(
        str(symbol).upper(),
        price_value,
        volume=volume_delta,
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
            "volume": volume_delta,
            "volume_source": "kite_cumulative_day_volume",
            "volume_cumulative_day_value": cumulative_volume_value,
            "volume_delta_status": volume_status,
            "volume_observation_complete": volume_complete,
            "volume_attribution": "CURRENT_SOURCE_TICK_MINUTE_ESTIMATE",
            "volume_is_estimate": True,
        },
    )
    if bool(result.get("accepted")):
        _LAST_SOURCE_TICK_EPOCH_BY_TOKEN[token] = tick_epoch
        if next_volume_baseline is not None:
            _LAST_CUMULATIVE_VOLUME_BY_TOKEN[token] = next_volume_baseline
    result["capture_identity"] = capture_identity
    result["delivery_observed"] = True
    result["bar_written"] = bool(result.get("accepted"))
    result["packet_kind"] = str(packet_kind or "")
    result["is_full_payload"] = bool(is_full_payload)
    result["live_evidence"] = not offline_fixture
    result["volume_delta_status"] = volume_status
    result["volume_observation_complete"] = volume_complete
    result["replay_fixture"] = offline_fixture
    if offline_fixture:
        result["fixture_kind"] = "OFFLINE_DETERMINISTIC_TEST"
    return result


__all__ = [
    "configure_live_source_session_store",
    "get_live_source_shadow_completed_bars",
    "persist_completed_live_source_shadow_bars",
    "record_live_source_shadow_tick",
    "reset_live_source_shadow_buffer",
    "shadow_ohlc_buffer",
]
