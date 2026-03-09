from __future__ import annotations

from core.freshness_policy import resolve_freshness_policy


def option_ltp_max_age_sec(
    mode: str | None,
    *,
    allow_stale_quotes: bool,
    live_sla: float,
    planning_sla: float,
) -> float:
    policy = resolve_freshness_policy(
        mode=mode,
        market_open=True,
        allow_stale_quotes=allow_stale_quotes,
        live_ltp_sec=float(live_sla),
        live_depth_sec=float(live_sla),
        planning_ltp_sec=float(planning_sla),
        planning_depth_sec=float(planning_sla),
        option_ok_live_sec=float(live_sla),
        option_ok_planning_sec=float(planning_sla),
        expiry_lotto_mode=False,
    )
    return float(policy.ltp_max_age_sec)
