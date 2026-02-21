"""Migration note:
Centralizes runtime market mode derivation in one authoritative helper.
Call derive_market_context() instead of ad-hoc EXECUTION_MODE/market_open checks.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from config import config as cfg
from core.time_utils import is_market_open_ist


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "is_market_open": bool(self.is_market_open),
            "require_live_quotes": bool(self.require_live_quotes),
            "allow_stale_quotes": bool(self.allow_stale_quotes),
        }


def _normalized_execution_mode(raw_mode: Any) -> str:
    mode = str(raw_mode or getattr(cfg, "EXECUTION_MODE", "SIM")).strip().upper()
    if mode == "LIVE":
        return "LIVE"
    # Canonical runtime simplification: non-LIVE execution behaves as SIM policy.
    return "SIM"


def _extract_segment(snapshot_or_config: Mapping[str, Any] | Any = None) -> str:
    segment = str(getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO"))
    if isinstance(snapshot_or_config, Mapping):
        seg = snapshot_or_config.get("segment")
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
    - SIM: non-LIVE execution modes
    """
    exec_mode = _normalized_execution_mode(
        execution_mode
        if execution_mode is not None
        else (
            snapshot_or_config.get("execution_mode")
            if isinstance(snapshot_or_config, Mapping)
            else getattr(snapshot_or_config, "EXECUTION_MODE", None)
        )
    )

    force_disable = bool(getattr(cfg, "OFFHOURS_FORCE_DISABLE", False))
    force_enable = (not force_disable) and bool(getattr(cfg, "OFFHOURS_FORCE_ENABLE", False))

    explicit_market_open = _to_bool_or_none(market_open)
    explicit_offhours = None
    if isinstance(snapshot_or_config, Mapping):
        if explicit_market_open is None:
            explicit_market_open = _to_bool_or_none(snapshot_or_config.get("market_open"))
        explicit_offhours = _to_bool_or_none(snapshot_or_config.get("offhours_mode"))
        if explicit_offhours is None:
            state = str(snapshot_or_config.get("state") or "").strip().upper()
            if state == "MARKET_CLOSED":
                explicit_offhours = True
    elif snapshot_or_config is not None and explicit_market_open is None:
        explicit_market_open = _to_bool_or_none(getattr(snapshot_or_config, "market_open", None))

    if force_enable:
        mode = "OFFHOURS" if exec_mode == "LIVE" else "SIM"
        is_market_open = False
    elif force_disable:
        mode = "LIVE" if exec_mode == "LIVE" else "SIM"
        is_market_open = bool(True if exec_mode == "LIVE" else (explicit_market_open if explicit_market_open is not None else False))
    else:
        if explicit_offhours is True:
            inferred_market_open = False
        elif explicit_market_open is not None:
            inferred_market_open = bool(explicit_market_open)
        else:
            seg = str(segment) if segment is not None else _extract_segment(snapshot_or_config)
            try:
                inferred_market_open = bool(is_market_open_ist(segment=seg))
            except Exception:
                # Fail closed for mode derivation: prefer stricter LIVE behavior if uncertain.
                inferred_market_open = bool(exec_mode != "LIVE")

        if exec_mode == "LIVE" and inferred_market_open:
            mode = "LIVE"
        elif exec_mode == "LIVE":
            mode = "OFFHOURS"
        else:
            mode = "SIM"
        is_market_open = bool(inferred_market_open)

    require_live_quotes = mode == "LIVE"
    allow_stale_quotes = mode in {"OFFHOURS", "SIM"}
    return MarketContext(
        mode=mode,
        is_market_open=bool(is_market_open),
        require_live_quotes=bool(require_live_quotes),
        allow_stale_quotes=bool(allow_stale_quotes),
    )


def is_offhours(snapshot_or_config: Mapping[str, Any] | Any = None) -> bool:
    return derive_market_context(snapshot_or_config).mode == "OFFHOURS"
