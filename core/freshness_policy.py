from __future__ import annotations

from dataclasses import dataclass


PROFILE_LIVE_STRICT = "LIVE_STRICT"
PROFILE_PAPER_RELAXED = "PAPER_RELAXED"
PROFILE_EXPIRY_LOTTO = "EXPIRY_LOTTO"


@dataclass(frozen=True)
class FreshnessPolicy:
    name: str
    option_ok_age_sec: float
    ltp_max_age_sec: float
    depth_max_age_sec: float
    ltp_required: bool
    depth_required: bool


def resolve_freshness_policy(
    *,
    mode: str | None,
    market_open: bool,
    allow_stale_quotes: bool,
    live_ltp_sec: float,
    live_depth_sec: float,
    planning_ltp_sec: float,
    planning_depth_sec: float,
    option_ok_live_sec: float,
    option_ok_planning_sec: float,
    expiry_lotto_mode: bool = False,
) -> FreshnessPolicy:
    mode_key = str(mode or "").strip().upper()
    strict_live = bool(mode_key in {"LIVE", "ARMED"} and market_open and (not allow_stale_quotes))
    if strict_live:
        return FreshnessPolicy(
            name=PROFILE_LIVE_STRICT,
            option_ok_age_sec=float(option_ok_live_sec),
            ltp_max_age_sec=float(live_ltp_sec),
            depth_max_age_sec=float(live_depth_sec),
            ltp_required=True,
            depth_required=True,
        )
    if bool(expiry_lotto_mode):
        return FreshnessPolicy(
            name=PROFILE_EXPIRY_LOTTO,
            option_ok_age_sec=float(min(max(option_ok_planning_sec, 5.0), planning_ltp_sec)),
            ltp_max_age_sec=float(planning_ltp_sec),
            depth_max_age_sec=float(planning_depth_sec),
            ltp_required=False,
            depth_required=False,
        )
    return FreshnessPolicy(
        name=PROFILE_PAPER_RELAXED,
        option_ok_age_sec=float(option_ok_planning_sec),
        ltp_max_age_sec=float(planning_ltp_sec),
        depth_max_age_sec=float(planning_depth_sec),
        ltp_required=False,
        depth_required=False,
    )

