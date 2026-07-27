from __future__ import annotations

CONTROL_FAMILIES = (
    "matched_time_random_direction",
    "direction_flip",
    "signal_time_jitter",
    "one_bar_delayed_entry",
    "two_bar_delayed_entry",
    "nifty_only_baseline",
    "alternate_eligible_strike",
    "alternate_eligible_expiry",
    "spread_stress",
    "slippage_stress",
    "cost_stress",
    "expiry_day_split",
    "volatility_regime_split",
    "concentration",
    "count_matched_control",
)


def require_control_family(name: str) -> None:
    if name not in CONTROL_FAMILIES:
        raise ValueError("unknown_control_family")
