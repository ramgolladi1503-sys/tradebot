from __future__ import annotations

import pandas as pd
import pytest

from research.residual_liquidity_exhaustion_mr_v2.stability_audit import (
    StabilityAuditContract,
    build_stability_screen,
    summarize_stability_screen,
    validate_event_ledger,
)


def _events(*, positive: bool, periods: int = 4, per_period: int = 15) -> pd.DataFrame:
    rows = []
    sign = 1.0 if positive else -1.0
    for period_index in range(periods):
        year = 2024 + period_index // 2
        half = 1 + period_index % 2
        for offset in range(per_period):
            day = 1 + offset
            row = {
                "event_time": f"{year}-{1 if half == 1 else 7:02d}-{day:02d} 10:00:00",
                "calendar_period": f"{year}H{half}",
                "target_symbol": "NIFTY",
                "event_side": "DOWN_SHOCK",
                "time_bucket": "MORNING_1000_1200",
                "magnitude_bucket": (
                    "RZ_2_2P5" if offset % 2 == 0 else "RZ_2P5_3"
                ),
                "volatility_bucket": (
                    "VOL_5_10BPS" if offset % 2 == 0 else "VOL_10_20BPS"
                ),
                "exhaustion_confirmed": True,
            }
            for horizon in (5, 15, 30, 60):
                value = sign * (2.0 + (offset % 3))
                row[f"raw_reversion_bps_{horizon}m"] = value
                row[f"confirmed_reversion_bps_{horizon}m"] = value
            rows.append(row)
    return pd.DataFrame(rows)


def test_missing_columns_fail_closed() -> None:
    with pytest.raises(ValueError, match="missing required columns"):
        validate_event_ledger(pd.DataFrame({"event_time": ["2026-01-01"]}))


def test_negative_campaign_closes_without_candidate() -> None:
    contract = StabilityAuditContract(
        minimum_events=20,
        minimum_sessions=20,
        minimum_calendar_periods=3,
        minimum_events_per_calendar_period=10,
        sign_flip_permutations=200,
    )
    screen = build_stability_screen(_events(positive=False), contract=contract)
    summary = summarize_stability_screen(screen, contract=contract)
    assert not screen["stable_candidate"].any()
    assert (
        summary["classification"]
        == "NO_STABLE_RESIDUAL_MEAN_REVERSION_SEGMENT_FOUND"
    )
    assert (
        summary["next_gate"]
        == "CLOSE_CANDLE_RESIDUAL_FORMULATION_AND_CONTINUE_DEPTH_DATA_ACQUISITION"
    )


def test_strong_recurrent_signal_is_only_diagnostic() -> None:
    contract = StabilityAuditContract(
        minimum_events=20,
        minimum_sessions=20,
        minimum_calendar_periods=3,
        minimum_events_per_calendar_period=10,
        sign_flip_permutations=500,
        false_discovery_rate=0.10,
    )
    screen = build_stability_screen(_events(positive=True), contract=contract)
    summary = summarize_stability_screen(screen, contract=contract)
    assert screen["stable_candidate"].any()
    assert summary["classification"] == (
        "DIAGNOSTIC_SEGMENTS_FOUND_REQUIRES_NEW_PREREGISTRATION_AND_UNSEEN_DATA"
    )
    assert summary["strategy_created"] is False
    assert summary["structural_edge_claim_allowed"] is False


def test_determinism_is_order_independent() -> None:
    contract = StabilityAuditContract(
        minimum_events=20,
        minimum_sessions=20,
        minimum_calendar_periods=3,
        minimum_events_per_calendar_period=10,
        sign_flip_permutations=200,
        false_discovery_rate=0.10,
    )
    events = _events(positive=True)
    first = build_stability_screen(events, contract=contract)
    second = build_stability_screen(
        events.sample(frac=1.0, random_state=7), contract=contract
    )
    columns = [
        "candidate_key",
        "stable_candidate",
        "sign_flip_p_value_15m",
        "sign_flip_p_value_30m",
        "bh_q_value_15m",
        "bh_q_value_30m",
    ]
    pd.testing.assert_frame_equal(first[columns], second[columns])
