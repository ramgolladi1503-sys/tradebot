from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pandas as pd

from .state_machine import (
    CAMPAIGN_ID,
    SPEC_VERSION,
    RPPV2Config,
    attach_forward_outcomes,
    attach_shifted_control,
    build_causal_location_map,
    evaluate_fixed_state_machine,
    label_zone_interactions,
    load_nifty_ohlc,
    sha256_path,
)

# This exact special-session set is already established by the governed
# constituent/index corpus policy used by prior physical certification. These
# dates are excluded because V2 claims a regular 09:15-15:30 NSE-session
# experiment, not because of any RPP outcome observed on them.
GOVERNED_SPECIAL_SESSIONS = frozenset(
    {
        "2024-01-20",
        "2024-03-02",
        "2024-05-18",
        "2024-11-01",
        "2025-02-01",
    }
)


def apply_governed_regular_session_policy(prices: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    present = sorted({str(x) for x in prices["session"].unique()})
    excluded = sorted(set(present) & set(GOVERNED_SPECIAL_SESSIONS))
    mask = ~prices["session"].astype(str).isin(GOVERNED_SPECIAL_SESSIONS)
    return prices.loc[mask].copy().reset_index(drop=True), excluded


def _deoverlap(events: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    keep: list[int] = []
    for _, day in events.sort_values("timestamp").groupby("session", sort=True):
        last = None
        for idx, row in day.iterrows():
            ts = row["timestamp"]
            if last is None or (ts - last) >= pd.Timedelta(minutes=minutes):
                keep.append(idx)
                last = ts
    return events.loc[keep].sort_values("timestamp").reset_index(drop=True)


def build_terminal_confirmed_events(states: pd.DataFrame, cfg: RPPV2Config) -> pd.DataFrame:
    """Create at most one forecast confirmation from each broken-zone context.

    A break may later satisfy both ACCEPTED and RECLAIMED semantics. Those are
    useful descriptive states, but the same original break is not allowed to
    become two separate forecasting bets. The first close-confirmed terminal
    state wins. REJECTED events are independent touch/rejection interactions.
    """
    if states.empty:
        return states.copy()
    mask = states["interaction_state"].isin(["REJECTED", "ACCEPTED", "RECLAIMED"])
    mask &= states["event_density_eligible"]
    ev = states.loc[mask].copy().sort_values("timestamp")
    ev["signal"] = np.where(ev["interaction_direction"] == "BULLISH", 1, -1)
    ev["event_type"] = ev["interaction_direction"] + "_" + ev["interaction_state"]

    rejection = ev[ev["interaction_state"] == "REJECTED"].copy()
    post_break = ev[ev["interaction_state"].isin(["ACCEPTED", "RECLAIMED"])].copy()
    if not post_break.empty:
        post_break = post_break.drop_duplicates(
            subset=["session", "zone_source_timestamp", "interaction_direction"],
            keep="first",
        )
    combined = pd.concat([rejection, post_break], ignore_index=True).sort_values("timestamp")
    return _deoverlap(combined, cfg.deoverlap_minutes)


def run_governed_experiment(
    input_path: str | Path,
    output_dir: str | Path,
    cfg: RPPV2Config = RPPV2Config(),
) -> dict:
    raw_prices = load_nifty_ohlc(input_path)
    prices_all, excluded_special = apply_governed_regular_session_policy(raw_prices)
    sessions_all = sorted(prices_all["session"].unique())

    if len(sessions_all) <= cfg.reserve_tail_sessions + cfg.warmup_sessions + cfg.test_sessions:
        report = {
            "campaign_id": CAMPAIGN_ID,
            "spec_version": SPEC_VERSION,
            "config_sha256": cfg.digest(),
            "verdict": "INSUFFICIENT_SESSIONS_FOR_FROZEN_EVALUATION",
            "session_count": len(sessions_all),
            "governed_special_session_policy_applied": True,
            "special_sessions_excluded": excluded_special,
            "one_forecast_confirmation_per_break": True,
            "holdout_evaluated": False,
            "option_pnl_claimed": False,
            "live_or_broker_authority": False,
        }
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return report

    # Seal the final regular-session tail before any profile construction.
    usable_sessions = sessions_all[: -cfg.reserve_tail_sessions]
    sealed_sessions = sessions_all[-cfg.reserve_tail_sessions :]
    prices = prices_all[prices_all["session"].isin(set(usable_sessions))].copy().reset_index(drop=True)

    location = build_causal_location_map(prices, cfg)
    states = label_zone_interactions(location, cfg)
    events = build_terminal_confirmed_events(states, cfg)
    outcomes = attach_forward_outcomes(events, prices, cfg)
    outcomes = attach_shifted_control(outcomes, prices, cfg)
    evaluation = evaluate_fixed_state_machine(outcomes, usable_sessions, cfg)

    report = {
        "campaign_id": CAMPAIGN_ID,
        "spec_version": SPEC_VERSION,
        "config_sha256": cfg.digest(),
        "input_path": str(Path(input_path)),
        "input_sha256": sha256_path(input_path),
        "raw_loaded_sessions_count": int(raw_prices["session"].nunique()),
        "all_regular_sessions_count": int(len(sessions_all)),
        "governed_special_session_policy_applied": True,
        "governed_special_session_set": sorted(GOVERNED_SPECIAL_SESSIONS),
        "special_sessions_excluded": excluded_special,
        "usable_sessions_count": int(len(usable_sessions)),
        "sealed_tail_sessions_count": int(len(sealed_sessions)),
        "sealed_tail_start": str(sealed_sessions[0]),
        "sealed_tail_end": str(sealed_sessions[-1]),
        "sealed_tail_feature_rows_processed": 0,
        "sealed_tail_outcomes_processed": 0,
        "price_rows_used": int(len(prices)),
        "location_rows": int(len(location)),
        "state_rows": int(len(states)),
        "confirmed_events": int(len(events)),
        "outcomes": int(len(outcomes)),
        "relative_density_is_calibrated_probability": False,
        "same_bar_zone_reselection_allowed": False,
        "first_break_is_trade_confirmation": False,
        "one_forecast_confirmation_per_break": True,
        "holdout_evaluated": False,
        "option_pnl_claimed": False,
        "live_or_broker_authority": False,
        **evaluation,
    }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    states.to_csv(out / "zone_interaction_states.csv", index=False)
    outcomes.to_csv(out / "confirmed_event_outcomes.csv", index=False)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return report
