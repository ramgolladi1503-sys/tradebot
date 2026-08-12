"""Migration note:
Centralizes runtime market mode derivation in one authoritative helper.
Call derive_market_context() instead of ad-hoc EXECUTION_MODE/market_open checks.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SESSION_NORMAL_OPEN = "NORMAL_OPEN"
SESSION_PRE_OPEN = "PRE_OPEN"
SESSION_PRE_OPEN_MATCHING = "PRE_OPEN_MATCHING"
SESSION_OPEN_WARMUP = "OPEN_WARMUP"
SESSION_POST_CLOSE = "POST_CLOSE"
SESSION_CLOSED = "CLOSED"


from config import config as cfg
from config.profile import resolve_trading_mode
from core.time_utils import is_market_open_ist, now_ist
from core.paths import regime_runtime_evidence_path

logger = logging.getLogger(__name__)

_NSE_FNO_SYMBOLS = {"NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY"}
_NSE_FNO_INSTRUMENTS = {"OPT", "FNO", "OPTION", "OPTIONS", "FUT", "FUTURE"}
_SEGMENT_COERCE_WARNED: set[tuple[str, str, str]] = set()


def _normalized_context_mapping(snapshot_or_config: Mapping[str, Any] | Any = None) -> Mapping[str, Any] | None:
    if not isinstance(snapshot_or_config, Mapping):
        return None
    merged: dict[str, Any] = {}
    nested = snapshot_or_config.get("market_context")
    if isinstance(nested, Mapping):
        merged.update(dict(nested))
    merged.update(dict(snapshot_or_config))
    merged.pop("market_context", None)
    return merged


def _to_bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


@dataclass(frozen=True)
class MarketContext:
    mode: str
    is_market_open: bool
    require_live_quotes: bool
    allow_stale_quotes: bool
    planning_only: bool
    session_state: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "is_market_open": bool(self.is_market_open),
            "require_live_quotes": bool(self.require_live_quotes),
            "allow_stale_quotes": bool(self.allow_stale_quotes),
            "planning_only": bool(self.planning_only),
            "session_state": self.session_state,
        }


def _normalized_execution_mode(raw_mode: Any) -> str:
    return resolve_trading_mode(raw_mode)


def _extract_segment(snapshot_or_config: Mapping[str, Any] | Any = None) -> str:
    segment = str(getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO"))
    normalized = _normalized_context_mapping(snapshot_or_config)
    if isinstance(normalized, Mapping):
        seg = normalized.get("segment")
        if seg is not None:
            segment = str(seg)
    elif snapshot_or_config is not None:
        seg = getattr(snapshot_or_config, "DEFAULT_SEGMENT", None)
        if seg is not None:
            segment = str(seg)
    return segment


def _extract_symbol_instrument(snapshot_or_config: Mapping[str, Any] | Any = None) -> tuple[str | None, str | None]:
    normalized = _normalized_context_mapping(snapshot_or_config)
    symbol = None
    instrument = None
    if isinstance(normalized, Mapping):
        raw_symbol = normalized.get("symbol") or normalized.get("underlying")
        raw_instrument = normalized.get("instrument") or normalized.get("instrument_type")
        symbol = str(raw_symbol).strip().upper() if raw_symbol not in (None, "") else None
        instrument = str(raw_instrument).strip().upper() if raw_instrument not in (None, "") else None
    return symbol, instrument


def derive_session_state_ist(current_time=None, **kwargs) -> str:
    from datetime import time
    now_time = current_time or now_ist()
    t = now_time.time()
    if t < time(9, 0): return SESSION_PRE_OPEN
    if t < time(9, 8): return SESSION_PRE_OPEN_MATCHING
    if t < time(9, 15): return SESSION_OPEN_WARMUP
    if t < time(15, 30): return SESSION_NORMAL_OPEN
    if t <= time(16, 0): return SESSION_POST_CLOSE
    return SESSION_CLOSED


def coerce_segment_for_market_context(
    segment: str | None,
    *,
    symbol: str | None = None,
    instrument: str | None = None,
) -> str:
    resolved_segment = str(segment or getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")).strip().upper() or "NSE_FNO"
    symbol_key = str(symbol or "").strip().upper()
    instrument_key = str(instrument or "").strip().upper()
    needs_nse_fno = bool(symbol_key in _NSE_FNO_SYMBOLS or instrument_key in _NSE_FNO_INSTRUMENTS)
    if needs_nse_fno and resolved_segment != "NSE_FNO":
        warn_key = (symbol_key or "UNKNOWN", instrument_key or "UNKNOWN", resolved_segment)
        if warn_key not in _SEGMENT_COERCE_WARNED:
            _SEGMENT_COERCE_WARNED.add(warn_key)
            logger.warning(
                "MARKET_CONTEXT_SEGMENT_COERCED now_ist=%s symbol=%s instrument=%s segment=%s->NSE_FNO",
                now_ist().isoformat(),
                symbol_key or "UNKNOWN",
                instrument_key or "UNKNOWN",
                resolved_segment,
            )
        return "NSE_FNO"
    return resolved_segment


def derive_market_context(
    snapshot_or_config: Mapping[str, Any] | Any = None,
    *,
    execution_mode: str | None = None,
    market_open: bool | None = None,
    segment: str | None = None,
) -> MarketContext:
    normalized = _normalized_context_mapping(snapshot_or_config)
    exec_mode = _normalized_execution_mode(
        execution_mode
        if execution_mode is not None
        else (
            normalized.get("execution_mode")
            if isinstance(normalized, Mapping)
            else getattr(snapshot_or_config, "EXECUTION_MODE", None)
        )
    )

    force_disable = bool(getattr(cfg, "OFFHOURS_FORCE_DISABLE", False))
    force_enable = (not force_disable) and bool(getattr(cfg, "OFFHOURS_FORCE_ENABLE", False))
    extracted_symbol, extracted_instrument = _extract_symbol_instrument(normalized or snapshot_or_config)
    resolved_segment = coerce_segment_for_market_context(
        str(segment) if segment is not None else _extract_segment(normalized or snapshot_or_config),
        symbol=extracted_symbol,
        instrument=extracted_instrument,
    )

    explicit_market_open = _to_bool_or_none(market_open)
    explicit_offhours = None
    if isinstance(normalized, Mapping):
        if explicit_market_open is None:
            explicit_market_open = _to_bool_or_none(normalized.get("market_open"))
        explicit_offhours = _to_bool_or_none(normalized.get("offhours_mode"))
        if explicit_offhours is None:
            state = str(normalized.get("state") or "").strip().upper()
            if state == "MARKET_CLOSED":
                explicit_offhours = True
    elif snapshot_or_config is not None and explicit_market_open is None:
        explicit_market_open = _to_bool_or_none(getattr(snapshot_or_config, "market_open", None))

    explicit_session_state = None
    if isinstance(normalized, Mapping) and normalized.get("session_state"):
        explicit_session_state = str(normalized.get("session_state")).strip().upper()

    session_state = explicit_session_state or derive_session_state_ist(segment=resolved_segment)

    if force_enable:
        mode = "OFFHOURS" if exec_mode == "LIVE" else exec_mode
        is_market_open = False
    elif force_disable:
        if exec_mode == "LIVE":
            mode = "LIVE"
            is_market_open = bool(explicit_market_open if explicit_market_open is not None else True)
        else:
            mode = exec_mode
            is_market_open = bool(explicit_market_open if explicit_market_open is not None else False)
    else:
        if explicit_offhours is True:
            inferred_market_open = False
        elif explicit_market_open is not None:
            inferred_market_open = bool(explicit_market_open)
        else:
            try:
                inferred_market_open = bool(is_market_open_ist(segment=resolved_segment))
            except Exception:
                inferred_market_open = bool(exec_mode != "LIVE")

        if exec_mode == "LIVE":
            mode = "LIVE" if inferred_market_open else "OFFHOURS"
        elif exec_mode == "PAPER":
            mode = "PAPER"
        else:
            mode = "SIM"
        is_market_open = bool(inferred_market_open)

    require_live_quotes = bool(mode == "LIVE" and is_market_open)
    allow_stale_quotes = bool(mode in {"OFFHOURS", "SIM", "PAPER"})
    planning_only = bool(mode == "OFFHOURS" or (mode in {"PAPER", "SIM"} and not is_market_open))
    if bool(getattr(cfg, "MARKET_CONTEXT_LOG_MODE", False)):
        logger.info(
            "MARKET_CONTEXT_DERIVED now_ist=%s segment=%s mode=%s market_open=%s exec_mode=%s",
            now_ist().isoformat(),
            resolved_segment,
            mode,
            bool(is_market_open),
            exec_mode,
        )
    try:
        import time
        import json
        source_value = str(normalized.get("source") or "").strip().lower()
        replay_evidence = bool(normalized.get("replay_mode")) or source_value in {"replay", "paper_replay"}
        timeline_path = (
            Path("runtime/strategy_validation/regime_timeline.jsonl")
            if replay_evidence
            else regime_runtime_evidence_path()
        )
        timeline_path.parent.mkdir(parents=True, exist_ok=True)
        
        regime = str(
            normalized.get("primary_regime") or normalized.get("regime") or normalized.get("regime_day") or "NEUTRAL"
        ).strip().upper() or "NEUTRAL"
        confidence = float(normalized.get("regime_confidence", 0.0) or 0.0)
        
        row = {
            "market_timestamp": normalized.get("market_timestamp") or str(time.time()),
            "symbol": extracted_symbol or "UNKNOWN",
            "tradebot_regime": regime,
            "selected_strategy": "Unknown",
            "source": "replay" if replay_evidence else "runtime",
            "source_file": normalized.get("source_file") or normalized.get("session_id") or ("replay" if replay_evidence else "market_context"),
        }
        for field in ("open", "high", "low", "close"):
            if field not in normalized:
                row.pop(field, None)
        with timeline_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception:
        pass

    return MarketContext(
        mode=mode,
        is_market_open=bool(is_market_open),
        require_live_quotes=bool(require_live_quotes),
        allow_stale_quotes=bool(allow_stale_quotes),
        planning_only=bool(planning_only),
        session_state=session_state,
    )


def is_offhours(snapshot_or_config: Mapping[str, Any] | Any = None) -> bool:
    return derive_market_context(snapshot_or_config).mode == "OFFHOURS"


def derive_regime_context(snapshot_or_config: Mapping[str, Any] | Any = None) -> dict[str, Any]:
    normalized = _normalized_context_mapping(snapshot_or_config) or {}
    regime = str(
        normalized.get("primary_regime")
        or normalized.get("regime")
        or normalized.get("regime_day")
        or "NEUTRAL"
    ).strip().upper() or "NEUTRAL"
    regime_probs = normalized.get("regime_probs")
    regime_confidence = None
    if isinstance(regime_probs, Mapping):
        try:
            regime_confidence = max(float(value) for value in regime_probs.values() if value is not None)
        except Exception:
            regime_confidence = None
    if regime_confidence is None:
        regime_confidence = _to_bool_or_none(normalized.get("regime_confidence"))
        if regime_confidence is None:
            try:
                regime_confidence = float(normalized.get("regime_confidence"))
            except Exception:
                regime_confidence = 0.5 if regime != "NEUTRAL" else 0.35
    try:
        ltp = float(normalized.get("ltp") or 0.0)
    except Exception:
        ltp = 0.0
    try:
        vwap = float(normalized.get("vwap") or ltp or 0.0)
    except Exception:
        vwap = ltp
    try:
        atr = float(normalized.get("atr") or 0.0)
    except Exception:
        atr = 0.0
    try:
        vwap_slope = float(normalized.get("vwap_slope") or 0.0)
    except Exception:
        vwap_slope = 0.0
    try:
        ltp_change_window = float(normalized.get("ltp_change_window") or normalized.get("ltp_change") or 0.0)
    except Exception:
        ltp_change_window = 0.0
    try:
        vol_z = float(normalized.get("vol_z") or 0.0)
    except Exception:
        vol_z = 0.0

    trend_mode = "SIDEWAYS"
    edge = (ltp - vwap) / max(abs(vwap), 1e-6) if vwap else 0.0
    directional_move = abs(ltp_change_window)
    if regime == "TREND":
        sideways_hint = not bool(edge or ltp_change_window or vwap_slope)
    else:
        sideways_hint = bool(
            regime in {"RANGE", "RANGE_VOLATILE", "NEUTRAL"}
            or (
                abs(vwap_slope) < float(getattr(cfg, "TREND_VWAP_FALLBACK_SLOPE_ABS_MIN", 0.0008))
                and directional_move <= max(atr * 0.25, 1e-6)
            )
        )
    if not sideways_hint:
        direction_hint = edge
        if abs(direction_hint) <= 1e-9:
            direction_hint = vwap_slope if abs(vwap_slope) > 1e-9 else ltp_change_window
        if direction_hint > 0:
            trend_mode = "BULLISH"
        elif direction_hint < 0:
            trend_mode = "BEARISH"
    range_mode = bool(sideways_hint or trend_mode == "SIDEWAYS")
    volatility_mode = "NORMAL"
    if regime in {"EVENT", "PANIC"} or vol_z >= float(getattr(cfg, "EVENT_VOL_Z", 1.0)):
        volatility_mode = "HIGH"
    elif vol_z <= -0.5:
        volatility_mode = "LOW"

    return {
        "regime": regime,
        "regime_confidence": float(regime_confidence or 0.0),
        "trend_mode": trend_mode,
        "range_mode": bool(range_mode),
        "volatility_mode": volatility_mode,
    }


def classify_strategy_regime_mode(snapshot_or_config: Mapping[str, Any] | Any = None) -> dict[str, Any]:
    regime_ctx = derive_regime_context(snapshot_or_config)
    normalized = _normalized_context_mapping(snapshot_or_config) or {}
    try:
        ltp = float(normalized.get("ltp") or 0.0)
    except Exception:
        ltp = 0.0
    try:
        vwap = float(normalized.get("vwap") or ltp or 0.0)
    except Exception:
        vwap = ltp
    try:
        atr = float(normalized.get("atr") or 0.0)
    except Exception:
        atr = 0.0
    try:
        ltp_change_window = float(normalized.get("ltp_change_window") or normalized.get("ltp_change") or 0.0)
    except Exception:
        ltp_change_window = 0.0
    try:
        vol_z = float(normalized.get("vol_z") or 0.0)
    except Exception:
        vol_z = 0.0

    directional_move_atr = abs(float(ltp_change_window)) / max(float(atr), 1e-6) if atr > 0 else 0.0
    regime_confidence = float(regime_ctx.get("regime_confidence") or 0.0)
    trend_mode = str(regime_ctx.get("trend_mode") or "SIDEWAYS").strip().upper()
    range_mode = bool(regime_ctx.get("range_mode"))
    volatility_mode = str(regime_ctx.get("volatility_mode") or "NORMAL").strip().upper()
    regime = str(regime_ctx.get("regime") or "NEUTRAL").strip().upper() or "NEUTRAL"
    vwap_edge = abs(float(ltp - vwap)) / max(abs(vwap), 1e-6) if vwap else 0.0
    trend_edge_min = max(
        float(getattr(cfg, "PLANNING_SIGNAL_VWAP_EDGE_MIN", 0.0008) or 0.0008),
        1e-6,
    )

    regime_mode = "UNCERTAIN"
    reasons: list[str] = []
    if regime_confidence < float(getattr(cfg, "STRATEGY_REGIME_UNCERTAIN_CONFIDENCE_MAX", 0.30) or 0.30):
        regime_mode = "UNCERTAIN"
        reasons.append("low_regime_confidence")
    elif range_mode or trend_mode == "SIDEWAYS":
        regime_mode = "SIDEWAYS"
        reasons.append("range_or_sideways")
    elif (
        trend_mode in {"BULLISH", "BEARISH"}
        and regime_confidence >= float(getattr(cfg, "STRATEGY_REGIME_CONFIDENCE_MIN", 0.45) or 0.45)
        and (
            directional_move_atr >= float(getattr(cfg, "STRATEGY_REGIME_TREND_ATR_MIN", 0.35) or 0.35)
            or vwap_edge >= trend_edge_min
        )
    ):
        regime_mode = "TRENDING"
        reasons.append("directional_persistence")
    elif (
        volatility_mode == "LOW"
        and directional_move_atr <= float(getattr(cfg, "STRATEGY_REGIME_LOW_VOL_ATR_MAX", 0.18) or 0.18)
        and abs(vol_z) <= float(getattr(cfg, "STRATEGY_REGIME_COMPRESSION_VOL_Z_MAX", 0.35) or 0.35)
    ):
        regime_mode = "LOW_VOL"
        reasons.append("compressed_low_vol")
    elif volatility_mode == "LOW":
        regime_mode = "LOW_VOL"
        reasons.append("low_volatility_mode")
    else:
        regime_mode = "UNCERTAIN"
        reasons.append("mixed_regime_signals")

    return {
        **dict(regime_ctx),
        "regime_mode": regime_mode,
        "directional_move_atr": round(float(directional_move_atr), 6),
        "regime_gate_reasons": reasons,
    }


def classify_session_mode(snapshot_or_config: Mapping[str, Any] | Any = None) -> dict[str, Any]:
    normalized = _normalized_context_mapping(snapshot_or_config) or {}
    market_ctx = derive_market_context(normalized or snapshot_or_config)
    try:
        minutes_since_open = float(normalized.get("minutes_since_open"))
    except Exception:
        minutes_since_open = None
    try:
        minutes_to_close = float(normalized.get("minutes_to_close"))
    except Exception:
        minutes_to_close = None

    opening_policy = cfg.get_session_policy("OPENING")
    midday_policy = cfg.get_session_policy("MIDDAY")
    closing_policy = cfg.get_session_policy("CLOSING")
    offhours_policy = cfg.get_session_policy("OFFHOURS")
    opening_window = max(0.0, float(opening_policy.get("opening_window_min") or 20.0))
    midday_start = max(opening_window, float(midday_policy.get("midday_start_min") or 60.0))
    closing_window = max(0.0, float(closing_policy.get("closing_window_min") or 35.0))

    session_mode = "OFFHOURS"
    reasons: list[str] = []
    if not bool(market_ctx.is_market_open) or str(market_ctx.mode).strip().upper() == "OFFHOURS":
        session_mode = "OFFHOURS"
        reasons.append("market_closed")
    elif minutes_since_open is not None and float(minutes_since_open) <= opening_window:
        session_mode = "OPENING"
        reasons.append("opening_window")
    elif minutes_to_close is not None and float(minutes_to_close) <= closing_window:
        session_mode = "CLOSING"
        reasons.append("closing_window")
    elif minutes_since_open is not None and float(minutes_since_open) >= midday_start:
        session_mode = "MIDDAY"
        reasons.append("midday_session")
    else:
        session_mode = "MIDDAY"
        reasons.append("default_live_session")

    penalty_map = {
        "OPENING": float(opening_policy.get("entry_penalty") or 0.02),
        "MIDDAY": float(midday_policy.get("entry_penalty") or 0.12),
        "CLOSING": float(closing_policy.get("entry_penalty") or 0.10),
        "OFFHOURS": float(offhours_policy.get("entry_penalty") or 0.20),
    }
    session_confidence = 1.0
    if minutes_since_open is None and minutes_to_close is None and session_mode != "OFFHOURS":
        session_confidence = 0.55
        reasons.append("missing_session_minutes")
    return {
        "session_mode": session_mode,
        "session_confidence": round(float(session_confidence), 6),
        "session_entry_penalty": round(float(penalty_map.get(session_mode, 0.0)), 6),
        "session_gate_reasons": reasons,
        "minutes_since_open": minutes_since_open,
        "minutes_to_close": minutes_to_close,
        "market_mode": market_ctx.mode,
    }
