from __future__ import annotations

import pandas as pd
import pytest

from research.constituent_lead_lag.model import DataContractError, TradeOutcome
from research.constituent_lead_lag.unweighted import (
    UnweightedThresholds,
    chronological_fold_summary,
    classify_unweighted_state,
    generate_unweighted_signal_states,
    select_universe_snapshot,
    validate_universe,
)


def test_current_snapshot_cannot_backfill_older_sessions():
    universe = validate_universe(
        pd.DataFrame([
            {
                "index_symbol": "NIFTY",
                "constituent_symbol": symbol,
                "effective_from": "2026-07-23",
            }
            for symbol in ["A", "B", "C", "D", "E"]
        ])
    )
    with pytest.raises(DataContractError, match="no point-in-time"):
        select_universe_snapshot(universe, "NIFTY", "2026-07-22")
    assert set(select_universe_snapshot(universe, "NIFTY", "2026-07-23")["constituent_symbol"]) == {"A", "B", "C", "D", "E"}


def test_unweighted_long_and_short_contract_is_symmetric():
    thresholds = UnweightedThresholds()
    long_side, _ = classify_unweighted_state(
        basket_return_5m_bps=12,
        basket_return_10m_bps=20,
        lead_gap_z=2.2,
        participation=0.8,
        breadth=0.5,
        dispersion_percentile=0.5,
        catch_up_ratio=0.4,
        range_consumed=0.4,
        constituent_coverage=0.9,
        thresholds=thresholds,
    )
    short_side, _ = classify_unweighted_state(
        basket_return_5m_bps=-12,
        basket_return_10m_bps=-20,
        lead_gap_z=-2.2,
        participation=0.8,
        breadth=-0.5,
        dispersion_percentile=0.5,
        catch_up_ratio=0.4,
        range_consumed=0.4,
        constituent_coverage=0.9,
        thresholds=thresholds,
    )
    assert long_side == "LONG"
    assert short_side == "SHORT"


def test_low_constituent_coverage_fails_closed():
    side, reason = classify_unweighted_state(
        basket_return_5m_bps=20,
        basket_return_10m_bps=30,
        lead_gap_z=3,
        participation=0.9,
        breadth=0.8,
        dispersion_percentile=0.2,
        catch_up_ratio=0.2,
        range_consumed=0.2,
        constituent_coverage=0.5,
        thresholds=UnweightedThresholds(),
    )
    assert side == "NONE"
    assert reason == "insufficient_constituent_coverage"


def _bar(timestamp, session, symbol, close, prior_close):
    return {
        "timestamp": timestamp,
        "session": session,
        "symbol": symbol,
        "open": prior_close,
        "high": max(prior_close, close),
        "low": min(prior_close, close),
        "close": close,
    }


def test_twenty_session_warmup_then_unweighted_signal_can_activate():
    dates = pd.bdate_range("2026-01-01", periods=21)
    rows = []
    components = ["A", "B", "C", "D", "E"]
    for number, day in enumerate(dates):
        session = day.strftime("%Y-%m-%d")
        times = [
            pd.Timestamp(f"{session} 09:50", tz="Asia/Kolkata").tz_convert("UTC"),
            pd.Timestamp(f"{session} 09:55", tz="Asia/Kolkata").tz_convert("UTC"),
            pd.Timestamp(f"{session} 10:00", tz="Asia/Kolkata").tz_convert("UTC"),
        ]
        index_prices = [100.0, 100.0, 100.0]
        for i, ts in enumerate(times):
            previous = index_prices[max(i - 1, 0)]
            rows.append(_bar(ts, session, "NIFTY", index_prices[i], previous))
        final_return_bps = float(number - 10) if number < 20 else 80.0
        for component_number, symbol in enumerate(components):
            dispersion_offset = (component_number - 2) * 0.2
            r5 = final_return_bps + dispersion_offset
            prices = [100.0, 100.0, 100.0 * (1.0 + r5 / 10_000.0)]
            for i, ts in enumerate(times):
                previous = prices[max(i - 1, 0)]
                rows.append(_bar(ts, session, symbol, prices[i], previous))

    universe = pd.DataFrame([
        {
            "index_symbol": "NIFTY",
            "constituent_symbol": symbol,
            "effective_from": dates[0].strftime("%Y-%m-%d"),
        }
        for symbol in components
    ])
    states = generate_unweighted_signal_states(
        pd.DataFrame(rows),
        universe,
        "NIFTY",
        decision_times=["10:00"],
        thresholds=UnweightedThresholds(
            minimum_constituent_count=5,
            dispersion_percentile_max=1.0,
        ),
    )
    assert [state.session for state in states] == [day.strftime("%Y-%m-%d") for day in dates]
    assert all(s.reason == "insufficient_lead_gap_history" for s in states[:20])
    assert states[-1].side == "LONG"
    assert states[-1].constituent_coverage == 1.0


def test_chronological_fold_summary_uses_session_order():
    outcomes = [
        TradeOutcome(
            index_symbol="NIFTY",
            session=f"2026-01-{day:02d}",
            decision_time="10:00",
            side="LONG",
            entry_timestamp="2026-01-01T04:35:00+00:00",
            exit_timestamp="2026-01-01T04:55:00+00:00",
            entry_price=100,
            exit_price=101,
            stop_bps=10,
            target_bps=15,
            gross_return_bps=float(day),
            net_return_bps=float(day),
            exit_reason="MAX_HOLD",
        )
        for day in range(1, 11)
    ]
    summary = chronological_fold_summary(outcomes, folds=5)
    assert [row["fold"] for row in summary["folds"]] == [1, 2, 3, 4, 5]
    assert summary["folds"][0]["session_start"] == "2026-01-01"
    assert summary["positive_mean_folds"] == 5
