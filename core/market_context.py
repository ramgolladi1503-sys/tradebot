"""Migration note:
Centralizes runtime market mode derivation in one authoritative helper.
Call derive_market_context() instead of ad-hoc EXECUTION_MODE/market_open checks.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from config import config as cfg
from config.profile import resolve_trading_mode
from core.time_utils import is_market_open_ist, now_ist

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "is_market_open": bool(self.is_market_open),
            "require_live_quotes": bool(self.require_live_quotes),
            "allow_stale_quotes": bool(self.allow_stale_quotes),
            "planning_only": bool(self.planning_only),
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
    """
    Authoritative runtime mode derivation.

    Mode semantics:
    - LIVE: execution mode LIVE and market open
    - OFFHOURS: execution mode LIVE and market closed
    - PAPER: execution mode PAPER
    - SIM: execution mode SIM (and unknown modes)
    """
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

    if force_enable:
        mode = "OFFHOURS" if exec_mode == "LIVE" else exec_mode
        is_market_open = False
    elif force_disable:
        if exec_mode == "LIVE":
            mode = "LIVE"
            is_market_open = bool(
                explicit_market_open if explicit_market_open is not None else True
            )
        else:
            mode = exec_mode
            is_market_open = bool(
                explicit_market_open if explicit_market_open is not None else False
            )
    else:
        if explicit_offhours is True:
            inferred_market_open = False
        elif explicit_market_open is not None:
            inferred_market_open = bool(explicit_market_open)
        else:
            try:
                inferred_market_open = bool(is_market_open_ist(segment=resolved_segment))
            except Exception:
                # Fail closed for mode derivation: prefer stricter LIVE behavior if uncertain.
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
    planning_only = bool(mode == "OFFHOURS")
    if bool(getattr(cfg, "MARKET_CONTEXT_LOG_MODE", False)):
        logger.info(
            "MARKET_CONTEXT_DERIVED now_ist=%s segment=%s mode=%s market_open=%s exec_mode=%s",
            now_ist().isoformat(),
            resolved_segment,
            mode,
            bool(is_market_open),
            exec_mode,
        )
    return MarketContext(
        mode=mode,
        is_market_open=bool(is_market_open),
        require_live_quotes=bool(require_live_quotes),
        allow_stale_quotes=bool(allow_stale_quotes),
        planning_only=bool(planning_only),
    )


def is_offhours(snapshot_or_config: Mapping[str, Any] | Any = None) -> bool:
    return derive_market_context(snapshot_or_config).mode == "OFFHOURS"
