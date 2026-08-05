from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from research.psilor_v1 import (
    PSILORError,
    assert_precomputed_outcome_reconciles,
    audit_bar_horizon,
    audit_psilor_data_readiness,
    black76_price,
    build_elapsed_time_trade,
    build_oracle_ladder,
    current_drive_option_schema_assessment,
    evaluate_event_location,
    evaluate_option_repricing_lag,
    event_signal_fingerprint,
    reconcile_long_return,
    resolve_long_barrier_exit,
)


SPEC = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "research/psilor_v1/spec.json"
    ).read_text()
)


def _event(**overrides):
    row = {
        "timestamp": "2026-08-05T10:00:00+05:30",
        "source_max_timestamp": "2026-08-05T10:00:00+05:30",
        "shock_direction": "DOWN",
        "participation_shock_z": 2.2,
        "index_underreaction_z": 1.6,
        "participation_persistence_z": 1.2,
        "participation_collapse_z": 1.3,
        "index_catchup_z": 1.0,
        "index_reversal_z": 1.1,
    }
    row.update(overrides)
    return row


def _repricing(
    option_type="CE",
    futures_change=50.0,
    observed_change=5.0,
):
    previous_futures = 25000.0
    current_futures = previous_futures + futures_change
    strike = 24850.0 if option_type == "CE" else 25150.0
    years = 3 / 365
    iv = 0.18
    previous_mid = black76_price(
        option_type,
        previous_futures,
        strike,
        years,
        iv,
        0.065,
    )
    return {
        "option_type": option_type,
        "previous_futures_price": previous_futures,
        "futures_price": current_futures,
        "strike": strike,
        "years_to_expiry": years,
        "previous_option_bid": previous_mid - 0.5,
        "previous_option_ask": previous_mid + 0.5,
        "option_bid": previous_mid + observed_change - 0.5,
        "option_ask": previous_mid + observed_change + 0.5,
        "previous_reference_iv": iv,
        "reference_iv": iv,
        "elapsed_seconds": 60,
        "quote_age_ms": 100,
        "available_ask_quantity": 130,
        "available_bid_quantity": 130,
        "futures_ofi_z": 2.0,
        "option_trade_imbalance_z": 1.5,
        "option_book_imbalance": 0.25,
        "dte": 3,
        "is_expiry_day": False,
        "tick_size": 0.05,
    }


def test_profitable_and_losing_returns_are_reconciled_from_prices():
    gross, net = reconcile_long_return(
        entry_price=100,
        exit_price=110,
        round_trip_cost_fraction=0.01,
    )
    assert gross == pytest.approx(0.10)
    assert net == pytest.approx(0.09)
    gross_loss, net_loss = reconcile_long_return(
        entry_price=100,
        exit_price=90,
        round_trip_cost_fraction=0.01,
    )
    assert gross_loss == pytest.approx(-0.10)
    assert net_loss == pytest.approx(-0.11)


def test_elapsed_time_trade_does_not_turn_fifteen_bars_into_seventy_five_minutes():
    timestamps = pd.date_range(
        "2026-08-05T09:15:00Z",
        periods=20,
        freq="5min",
    )
    frame = pd.DataFrame(
        {"timestamp": timestamps, "close": range(100, 120)}
    )
    trade = build_elapsed_time_trade(
        frame,
        signal_timestamp=timestamps[0],
        entry_delay_seconds=1,
        hold_seconds=15 * 60,
    )
    assert trade.entry_row_index == 1
    assert trade.exit_row_index == 4
    assert trade.elapsed_seconds == 15 * 60


def test_bar_horizon_audit_detects_mixed_intervals():
    first = pd.date_range(
        "2026-08-05T09:15:00Z",
        periods=20,
        freq="1min",
    )
    second = pd.date_range(
        first[-1] + pd.Timedelta(minutes=5),
        periods=20,
        freq="5min",
    )
    frame = pd.DataFrame({"timestamp": list(first) + list(second)})
    audit = audit_bar_horizon(frame, horizon_bars=15)
    assert audit["mixed_elapsed_horizon"] is True
    assert audit["minimum_elapsed_seconds"] == 15 * 60
    assert audit["maximum_elapsed_seconds"] == 75 * 60


def test_precomputed_outcome_mismatch_fails():
    timestamps = pd.date_range(
        "2026-08-05T09:15:00Z",
        periods=5,
        freq="5min",
    )
    frame = pd.DataFrame(
        {"timestamp": timestamps, "close": [100, 101, 102, 103, 104]}
    )
    trade = build_elapsed_time_trade(
        frame,
        signal_timestamp=timestamps[0],
        entry_delay_seconds=1,
        hold_seconds=10 * 60,
    )
    with pytest.raises(PSILORError, match="does not reconcile"):
        assert_precomputed_outcome_reconciles(0.50, trade)


def test_ambiguous_stop_target_is_conservative_stop_first():
    result = resolve_long_barrier_exit(
        bar_open=100,
        bar_high=120,
        bar_low=80,
        stop_price=90,
        target_price=110,
    )
    assert result == {
        "exit_price": 90.0,
        "reason": "AMBIGUOUS_STOP_FIRST",
    }


def test_event_reversal_and_continuation_map_to_correct_option_types():
    reversal = evaluate_event_location(
        _event(),
        specification=SPEC,
        branch="REVERSAL",
    )
    continuation = evaluate_event_location(
        _event(),
        specification=SPEC,
        branch="CONTINUATION",
    )
    assert reversal["eligible"] is True
    assert reversal["trade_direction"] == "BULLISH"
    assert reversal["option_type"] == "CE"
    assert continuation["eligible"] is True
    assert continuation["trade_direction"] == "BEARISH"
    assert continuation["option_type"] == "PE"


def test_event_future_leak_fails_closed():
    row = _event(realized_return=0.99)
    with pytest.raises(PSILORError, match="future/outcome fields"):
        evaluate_event_location(
            row,
            specification=SPEC,
            branch="REVERSAL",
        )


def test_event_fingerprint_ignores_outcome_mutation():
    first = _event()
    second = copy.deepcopy(first)
    first["realized_return"] = 1.0
    second["realized_return"] = -1.0
    assert event_signal_fingerprint(
        [first],
        specification=SPEC,
        branch="REVERSAL",
    ) == event_signal_fingerprint(
        [second],
        specification=SPEC,
        branch="REVERSAL",
    )


def test_underpriced_option_is_eligible_and_uses_ask_entry_bid_exit():
    result = evaluate_option_repricing_lag(
        _repricing(),
        specification=SPEC,
        expected_option_type="CE",
    )
    assert result["eligible"] is True
    assert result["entry_quote_side"] == "ASK"
    assert result["exit_quote_side"] == "BID"
    assert result["repricing_lag"] > result["required_cost_buffer"]


def test_repricing_already_closed_is_rejected():
    result = evaluate_option_repricing_lag(
        _repricing(observed_change=100.0),
        specification=SPEC,
        expected_option_type="CE",
    )
    assert result["eligible"] is False
    assert "REPRICING_LAG_NOT_EXECUTABLE" in result["rejection_reasons"]


def test_missing_quote_quantity_fails_closed():
    row = _repricing()
    row.pop("available_ask_quantity")
    with pytest.raises(PSILORError, match="missing fields"):
        evaluate_option_repricing_lag(
            row,
            specification=SPEC,
            expected_option_type="CE",
        )


def test_ltp_spread_trap_cannot_override_bid_exit_loss():
    gross, net = reconcile_long_return(
        entry_price=105,
        exit_price=95,
        round_trip_cost_fraction=0.0,
    )
    fake_ltp_return = 110 / 105 - 1
    assert fake_ltp_return > 0
    assert gross < 0
    assert net < 0


def test_cost_monotonicity():
    _, net_low = reconcile_long_return(
        entry_price=100,
        exit_price=105,
        round_trip_cost_fraction=0.001,
    )
    _, net_high = reconcile_long_return(
        entry_price=100,
        exit_price=105,
        round_trip_cost_fraction=0.01,
    )
    assert net_high < net_low


def test_current_drive_schema_is_truthfully_data_blocked():
    result = current_drive_option_schema_assessment()
    assert result["ready"] is False
    blockers = "\n".join(result["blockers"])
    assert "OPTION_FIELDS_MISSING:ask_quantity,bid_quantity" in blockers
    assert "MISSING_EVENT_DATASET" in blockers
    assert "MISSING_FUTURES_DATASET" in blockers
    assert "MISSING_INSTRUMENT_MASTER_DATASET" in blockers


def test_complete_synthetic_schema_and_sessions_pass_readiness():
    dates = pd.bdate_range("2026-01-01", periods=30)
    event_rows = pd.DataFrame(
        [
            {
                "timestamp": date,
                "source_max_timestamp": date,
                "shock_direction": "UP",
                "participation_shock_z": 1.0,
                "index_underreaction_z": 1.0,
                "participation_persistence_z": 1.0,
                "participation_collapse_z": 1.0,
                "index_catchup_z": 1.0,
                "index_reversal_z": 1.0,
            }
            for date in dates
        ]
    )
    futures = pd.DataFrame(
        [
            {
                "ts": date,
                "instrument_key": "FUT",
                "bid_price": 1.0,
                "ask_price": 1.1,
                "bid_quantity": 100,
                "ask_quantity": 100,
                "volume": 1000,
            }
            for date in dates
        ]
    )
    options = futures.copy()
    for column in ["delta", "theta", "gamma", "vega", "iv"]:
        options[column] = 1.0
    master_columns = [
        "instrument_key",
        "tradingsymbol",
        "name",
        "expiry",
        "strike",
        "instrument_type",
        "segment",
        "exchange",
        "lot_size",
    ]
    result = audit_psilor_data_readiness(
        event_rows=event_rows,
        futures_ticks=futures,
        option_ticks=options,
        instrument_master=master_columns,
    )
    assert result["ready"] is True
    assert result["overlapping_sessions"] == 30


def test_oracle_ladder_is_monotonic_and_exposes_implementation_loss():
    frame = pd.DataFrame(
        {
            "market_opportunity": [1, 1, 1, 1],
            "event_location_correct": [1, 1, 1, 0],
            "direction_correct": [1, 1, 0, 0],
            "contract_correct": [1, 0, 0, 0],
            "exit_positive": [1, 0, 0, 0],
            "implementable_positive": [0, 0, 0, 0],
        }
    )
    result = build_oracle_ladder(frame)
    assert result["stage_counts"]["market_opportunity"] == 4
    assert result["stage_counts"]["event_location_correct"] == 3
    assert result["stage_counts"]["implementable_positive"] == 0
