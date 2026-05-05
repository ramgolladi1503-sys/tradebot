from __future__ import annotations

from typing import Any

DEFAULT_PRO_STRATEGY_REGISTRY: dict[str, dict[str, Any]] = {
    "vol_expansion": {
        "enabled": True,
        "state": "SHADOW",
        "allowed_regimes": ["TREND", "VOLATILE", "EVENT", "EXPIRY"],
    },
    "liquidity_imbalance": {
        "enabled": True,
        "state": "SHADOW",
        "allowed_regimes": ["TREND", "VOLATILE", "EVENT", "EXPIRY", "NEUTRAL"],
    },
    "vwap_mean_reversion": {
        "enabled": True,
        "state": "SHADOW",
        "allowed_regimes": ["RANGE", "NEUTRAL"],
    },
    "options_flow_alignment": {
        "enabled": True,
        "state": "SHADOW",
        "allowed_regimes": ["TREND", "VOLATILE", "EVENT", "EXPIRY", "NEUTRAL"],
    },
    "time_window_momentum": {
        "enabled": True,
        "state": "SHADOW",
        "allowed_regimes": ["TREND", "VOLATILE", "EVENT", "EXPIRY", "NEUTRAL"],
    },
}


def get_strategy_config(strategy: str, registry: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    source = registry or DEFAULT_PRO_STRATEGY_REGISTRY
    return dict(source.get(str(strategy), {"enabled": False, "state": "DISABLED", "allowed_regimes": []}))


def strategy_enabled_for_regime(
    strategy: str,
    regime: str,
    *,
    registry: dict[str, dict[str, Any]] | None = None,
    min_state: str = "SHADOW",
) -> bool:
    cfg = get_strategy_config(strategy, registry)
    if not bool(cfg.get("enabled", False)):
        return False
    allowed = {str(x).upper() for x in list(cfg.get("allowed_regimes") or [])}
    if allowed and str(regime).upper() not in allowed:
        return False
    order = ["DISABLED", "SHADOW", "PAPER", "PILOT", "LIVE"]
    state = str(cfg.get("state") or "DISABLED").upper()
    min_state = str(min_state or "SHADOW").upper()
    return order.index(state if state in order else "DISABLED") >= order.index(min_state if min_state in order else "SHADOW")
