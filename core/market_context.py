"""Migration note:
Centralizes runtime market mode derivation in one authoritative helper.
Call derive_market_context() instead of ad-hoc EXECUTION_MODE/market_open checks.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from config import config as cfg
from config.profile import resolve_trading_mode
from core.time_utils import is_market_open_ist


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
            seg = str(segment) if segment is not None else _extract_segment(normalized or snapshot_or_config)
            try:
                inferred_market_open = bool(is_market_open_ist(segment=seg))
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
    planning_only = bool(mode in {"OFFHOURS", "SIM", "PAPER"})
    return MarketContext(
        mode=mode,
        is_market_open=bool(is_market_open),
        require_live_quotes=bool(require_live_quotes),
        allow_stale_quotes=bool(allow_stale_quotes),
        planning_only=bool(planning_only),
    )


def is_offhours(snapshot_or_config: Mapping[str, Any] | Any = None) -> bool:
    return derive_market_context(snapshot_or_config).mode == "OFFHOURS"
