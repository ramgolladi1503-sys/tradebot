from __future__ import annotations

import logging
from typing import Any

from core.events import append_event
from core.regime_canonical import ROUTER_CANONICAL_REGIMES, resolve_strategy_regime_label

logger = logging.getLogger(__name__)

_CANONICAL_REGIMES = set(ROUTER_CANONICAL_REGIMES) - {"UNKNOWN"}

# Strategy thresholds moved to strategies / core.strategy_profiles

_last_regime_emitted = None


def resolve_strategy_regime(raw_regime: Any, *, bias: Any = None, expiry_context: bool = False) -> str:
    global _last_regime_emitted

    regime = resolve_strategy_regime_label(raw_regime, bias=bias, expiry_context=expiry_context)

    if _last_regime_emitted is not None and _last_regime_emitted != regime:
        append_event("regime_transition", {
            "previous_regime": _last_regime_emitted,
            "new_regime": regime,
            "raw_input": str(raw_regime),
            "bias_input": str(bias),
        })
        logger.info("regime_transition previous=%s new=%s", _last_regime_emitted, regime)

    _last_regime_emitted = regime
    return regime


# get_strategy_regime_profile has been moved out of this module

def record_strategy_regime_path(
    strategy_name: str,
    regime: str,
    profile: dict[str, Any],
    *,
    debug_stats: dict[str, Any] | None = None,
) -> None:
    payload = {
        "strategy": str(strategy_name),
        "regime": str(regime),
        "setup_family": str(profile.get("setup_family") or ""),
        "variant": str(profile.get("variant") or ""),
        "score_bias": float(profile.get("score_bias") or 0.0),
        "vwap_buffer_mult": float(profile.get("vwap_buffer_mult") or 1.0),
        "min_move_mult": float(profile.get("min_move_mult") or 1.0),
    }
    if isinstance(debug_stats, dict):
        debug_stats["regime_path"] = payload
    logger.info(
        "strategy_regime_path strategy=%s regime=%s setup_family=%s variant=%s score_bias=%.3f vwap_buffer_mult=%.3f min_move_mult=%.3f",
        payload["strategy"],
        payload["regime"],
        payload["setup_family"],
        payload["variant"],
        payload["score_bias"],
        payload["vwap_buffer_mult"],
        payload["min_move_mult"],
    )
