"""Runtime bridge from the legacy OHLC buffer to durable Market Session Memory V1.

The existing global ``ohlc_buffer`` remains the hot cache. This contract makes it
write-through/read-through for trusted live 1-minute bars while keeping newly
constructed ``OhlcBuffer()`` instances memory-only unless a store is explicitly
supplied. That preserves replay/test isolation.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.market_session_store import market_session_store

_INSTALLED = False
_SEALED_DAYS: set[str] = set()


def _same_minute_resolution(bars: list[dict], idx: int) -> bool:
    try:
        ts = bars[idx].get("ts")
        if not isinstance(ts, datetime):
            return False
        for other in (idx - 1, idx + 1):
            if 0 <= other < len(bars):
                ots = bars[other].get("ts")
                if isinstance(ots, datetime) and abs((ots - ts).total_seconds()) == 60:
                    return True
    except Exception:
        return False
    return False


def _persist(buffer, symbol: str, bar: dict, *, allow_historical_seed: bool = False) -> dict:
    store = getattr(buffer, "_session_store", None)
    if store is None:
        return {"persisted": False, "status": "NO_SESSION_STORE"}
    provenance = dict(bar.get("bar_provenance") or {})
    source = str(provenance.get("source_type") or "unknown").strip().lower()
    if bool(provenance.get("replay_fixture")) or source == "replay_fixture":
        return {"persisted": False, "status": "SKIPPED_REPLAY_FIXTURE"}
    if bool(provenance.get("non_live_fallback")) or bool(provenance.get("recovered_synthetic")):
        return {"persisted": False, "status": "SKIPPED_NON_LIVE_SOURCE"}
    if bool(provenance.get("historical_seed")) or source == "historical_seed":
        if not allow_historical_seed:
            return {"persisted": False, "status": "SKIPPED_UNPROVEN_HISTORICAL_RESOLUTION"}
    elif source not in {"live_websocket", "tick_store_live", "deterministic_test"}:
        return {"persisted": False, "status": f"SKIPPED_UNTRUSTED_SOURCE:{source}"}
    try:
        result = store.persist_completed_bar(symbol, bar)
        return {"persisted": bool(result.get("persisted")), "status": str(result.get("status") or "UNKNOWN")}
    except Exception as exc:
        return {"persisted": False, "status": f"PERSIST_FAILED:{type(exc).__name__}:{exc}"}


def _install_ohlc_contract() -> None:
    try:
        from core import ohlc_buffer as module
    except Exception:
        return
    cls = getattr(module, "OhlcBuffer", None)
    global_buffer = getattr(module, "ohlc_buffer", None)
    if cls is None or global_buffer is None or getattr(cls, "_market_session_memory_v1", False):
        return

    original_init = cls.__init__
    original_update = cls.update_tick
    original_completed = cls.get_completed_bars

    def init(self, *args, session_store=None, **kwargs):
        original_init(self, *args, **kwargs)
        self._session_store = session_store

    def update_tick(self, symbol, price, volume=None, ts=None, provenance=None):
        result = original_update(self, symbol, price, volume=volume, ts=ts, provenance=provenance)
        if isinstance(result, dict) and result.get("accepted") and result.get("status") == "NEW_BAR":
            previous_bucket = result.get("current_tail_bucket")
            prior = None
            try:
                prior = next((b for b in reversed(list(self._bars.get(symbol, []))) if b.get("ts") == previous_bucket), None)
            except Exception:
                prior = None
            if prior is not None:
                persisted = _persist(self, symbol, prior)
                result = dict(result)
                result["session_memory_persisted"] = bool(persisted["persisted"])
                result["session_memory_status"] = persisted["status"]
        return result

    def get_completed_bars(self, symbol, *, as_of, interval_seconds=60):
        local = original_completed(self, symbol, as_of=as_of, interval_seconds=interval_seconds)
        store = getattr(self, "_session_store", None)
        if store is None or not isinstance(as_of, datetime) or int(interval_seconds) != 60:
            return local
        try:
            source_bars = list(self._bars.get(symbol, []))
            for idx, bar in enumerate(source_bars):
                ts = bar.get("ts")
                if not isinstance(ts, datetime) or ts + timedelta(seconds=60) > as_of:
                    continue
                prov = dict(bar.get("bar_provenance") or {})
                is_hist = bool(prov.get("historical_seed")) or str(prov.get("source_type") or "").lower() == "historical_seed"
                _persist(self, symbol, bar, allow_historical_seed=(is_hist and _same_minute_resolution(source_bars, idx)))
            durable = store.get_bars(symbol, as_of=as_of, timeframe="1m")
            merged = {}
            for row in durable:
                merged[row.get("ts")] = dict(row)
            for row in local:
                merged[row.get("ts")] = dict(row)
            return [merged[key] for key in sorted(merged) if key is not None]
        except Exception:
            return local

    def get_session_bars(self, symbol, *, as_of, timeframe="1m"):
        store = getattr(self, "_session_store", None)
        if store is None:
            return original_completed(self, symbol, as_of=as_of) if timeframe == "1m" else []
        return store.get_bars(symbol, as_of=as_of, timeframe=timeframe)

    def get_session_context(self, symbol, *, as_of):
        store = getattr(self, "_session_store", None)
        if store is None:
            bars = original_completed(self, symbol, as_of=as_of)
            return {"authoritative": False, "source": "in_memory_only", "symbol": str(symbol).upper(), "bars": {"1m": len(bars)}}
        return store.build_context(symbol, as_of=as_of)

    cls.__init__ = init
    cls.update_tick = update_tick
    cls.get_completed_bars = get_completed_bars
    cls.get_session_bars = get_session_bars
    cls.get_session_context = get_session_context
    cls._market_session_memory_v1 = True
    global_buffer._session_store = market_session_store


def _compact_feature_payload(row: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "ltp", "vwap", "atr", "adx_14", "vwap_slope", "rsi", "rsi_mom", "vol_z",
        "atr_pct", "ltp_change", "ltp_change_5m", "ltp_change_10m", "ltp_acceleration",
        "regime", "primary_regime", "regime_confidence", "regime_entropy", "regime_transition_rate",
        "day_type", "day_confidence", "orb_bias", "orb_high", "orb_low", "minutes_since_open",
        "depth_imbalance", "option_chain_skew", "oi_delta", "iv_mean", "quote_source",
        "quote_age_sec", "candle_ts_epoch", "ohlc_bars_count", "system_state", "warmup_status",
    )
    return {field: row.get(field) for field in fields if field in row}


def _install_market_data_contract() -> None:
    try:
        from core import market_data as md
    except Exception:
        return
    original = getattr(md, "fetch_live_market_data", None)
    if not callable(original) or getattr(original, "_market_session_memory_v1", False):
        return

    def fetch_with_session_memory(*args, **kwargs):
        rows = original(*args, **kwargs)
        store = market_session_store
        if store is None:
            return rows
        symbols = set()
        for row in list(rows or []):
            if not isinstance(row, dict) or not row.get("valid", True):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            if str(row.get("instrument") or "OPT").upper() not in {"OPT", "EQ"}:
                continue
            as_of = row.get("timestamp_ist") or row.get("timestamp")
            if as_of is None:
                continue
            try:
                context = store.build_context(symbol, as_of=as_of)
                row["session_memory"] = context
                row["session_memory_available"] = True
                store.persist_feature_snapshot(symbol, as_of=as_of, payload=_compact_feature_payload(row))
                symbols.add(symbol)
            except Exception as exc:
                row["session_memory_available"] = False
                row["session_memory_error"] = f"{type(exc).__name__}:{exc}"
        try:
            if rows:
                first_ts = next((r.get("timestamp_ist") for r in rows if isinstance(r, dict) and r.get("timestamp_ist")), None)
                when = datetime.fromisoformat(str(first_ts)) if first_ts else None
                if when is not None and when.tzinfo is not None and when.time() >= datetime.strptime("15:30", "%H:%M").time():
                    day = when.date().isoformat()
                    if day not in _SEALED_DAYS:
                        configured = [str(s).upper() for s in (getattr(md.cfg, "SYMBOLS", []) or []) if str(s).strip()]
                        store.seal_session(day, configured or sorted(symbols))
                        _SEALED_DAYS.add(day)
        except Exception:
            pass
        return rows

    fetch_with_session_memory._market_session_memory_v1 = True
    md.fetch_live_market_data = fetch_with_session_memory
    md.get_session_bars = lambda symbol, *, as_of, timeframe="1m": store_get_bars(symbol, as_of=as_of, timeframe=timeframe)
    md.get_session_context = lambda symbol, *, as_of: store_get_context(symbol, as_of=as_of)
    md.seal_market_session = lambda session_date, symbols=None: store_seal(session_date, symbols=symbols, cfg=md.cfg)


def store_get_bars(symbol: str, *, as_of, timeframe: str = "1m"):
    if market_session_store is None:
        return []
    return market_session_store.get_bars(symbol, as_of=as_of, timeframe=timeframe)


def store_get_context(symbol: str, *, as_of):
    if market_session_store is None:
        return {"authoritative": False, "source": "session_memory_disabled", "symbol": str(symbol).upper()}
    return market_session_store.build_context(symbol, as_of=as_of)


def store_seal(session_date: str, *, symbols=None, cfg=None):
    if market_session_store is None:
        return {"status": "FAIL", "reason": "session_memory_disabled"}
    configured = list(symbols or (getattr(cfg, "SYMBOLS", []) if cfg is not None else []) or [])
    return market_session_store.seal_session(str(session_date), configured)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_ohlc_contract()
    _install_market_data_contract()
    _INSTALLED = True
