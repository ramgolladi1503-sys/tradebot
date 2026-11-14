from __future__ import annotations

import pandas as pd

from research.nifty_option_edge import (
    CLAIM_BOUNDARY_OPTION_REALIZED,
    ForecastSignal,
    ForwardMoveLabelConfig,
    StrikeRankingConfig,
    compute_forward_move_labels,
    evaluate_direction_magnitude_forecasts,
    rank_option_strikes,
    realized_option_pnl_from_quotes,
)


def test_forward_labels_use_next_open_and_fail_at_session_boundary() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-05 09:15", periods=7, freq="min", tz="Asia/Kolkata").tz_convert("UTC"),
            "session_date": ["2026-01-05"] * 4 + ["2026-01-06"] * 3,
            "open": [100, 101, 102, 103, 200, 201, 202],
            "high": [101, 103, 104, 105, 201, 203, 204],
            "low": [99, 100, 101, 102, 199, 200, 201],
            "close": [100.5, 102, 103, 104, 200.5, 202, 203],
        }
    )
    labels = compute_forward_move_labels(
        bars,
        config=ForwardMoveLabelConfig(
            horizons_minutes=(2,),
            move_thresholds_points=(1.0, 2.0),
        ),
    )
    assert labels.loc[0, "fwd_2m_entry_price"] == 101
    assert labels.loc[0, "fwd_2m_terminal_close"] == 103
    assert labels.loc[0, "fwd_2m_signed_points"] == 2
    assert labels.loc[2, "fwd_2m_status"] == "SESSION_ENDED_BEFORE_HORIZON"


def test_bullish_forecast_competes_ce_moneyness_and_selects_positive_net() -> None:
    chain = pd.DataFrame(
        [
            {"instrument": "NIFTY_TEST_23900_CE", "strike": 23900, "option_type": "CE", "bid": 130, "ask": 132, "delta": 0.62, "gamma": 0.003, "theta": -18, "volume": 1000, "open_interest": 5000},
            {"instrument": "NIFTY_TEST_23950_CE", "strike": 23950, "option_type": "CE", "bid": 101, "ask": 102, "delta": 0.51, "gamma": 0.004, "theta": -16, "volume": 2000, "open_interest": 6000},
            {"instrument": "NIFTY_TEST_24000_CE", "strike": 24000, "option_type": "CE", "bid": 74, "ask": 75, "delta": 0.39, "gamma": 0.0045, "theta": -13, "volume": 3000, "open_interest": 7000},
            {"instrument": "NIFTY_TEST_23950_PE", "strike": 23950, "option_type": "PE", "bid": 95, "ask": 97, "delta": -0.49, "gamma": 0.004, "theta": -16, "volume": 4000, "open_interest": 8000},
        ]
    )
    forecast = ForecastSignal(
        decision_timestamp="2026-01-05T10:00:00+05:30",
        direction="BULLISH",
        horizon_minutes=20,
        probability_direction=0.72,
        expected_spot_move_points=50.0,
    )
    decision = rank_option_strikes(
        chain,
        spot=23950,
        forecast=forecast,
        config=StrikeRankingConfig(max_spread_pct=5.0),
    )
    assert decision.status == "SELECTED"
    assert decision.selected is not None
    assert decision.selected["option_type"] == "CE"
    assert all(item["option_type"] == "CE" for item in decision.candidates)
    assert {item["moneyness"] for item in decision.candidates} == {"ITM", "ATM", "OTM"}
    assert decision.selected["expected_net_premium_points"] > 0


def test_small_move_is_no_trade_before_strike_selection() -> None:
    chain = pd.DataFrame(
        [{"strike": 23950, "option_type": "CE", "bid": 100, "ask": 102, "delta": 0.5}]
    )
    forecast = ForecastSignal(
        decision_timestamp="2026-01-05T10:00:00+05:30",
        direction="BULLISH",
        horizon_minutes=15,
        probability_direction=0.75,
        expected_spot_move_points=5.0,
    )
    decision = rank_option_strikes(chain, spot=23950, forecast=forecast)
    assert decision.status == "NO_TRADE"
    assert decision.reason == "forecast_move_below_threshold"


def test_missing_bid_ask_fails_closed() -> None:
    chain = pd.DataFrame(
        [{"strike": 23950, "option_type": "PE", "last_price": 100, "delta": -0.5}]
    )
    forecast = ForecastSignal(
        decision_timestamp="2026-01-05T10:00:00+05:30",
        direction="BEARISH",
        horizon_minutes=15,
        probability_direction=0.70,
        expected_spot_move_points=-40.0,
    )
    decision = rank_option_strikes(chain, spot=23950, forecast=forecast)
    assert decision.status == "NO_TRADE"
    assert "option_chain_missing_required_fields" in decision.reason


def test_realized_long_option_pnl_is_ask_to_bid_after_costs() -> None:
    result = realized_option_pnl_from_quotes(
        entry_ask=100.0,
        exit_bid=112.0,
        slippage_points_round_trip=1.0,
        fees_points_round_trip=0.5,
        lot_size=50,
    )
    assert result["pnl_points"] == 10.5
    assert result["pnl_rupees_per_lot"] == 525.0
    assert result["claim_boundary"] == CLAIM_BOUNDARY_OPTION_REALIZED


def test_forecast_evaluation_scores_direction_and_magnitude_selectively() -> None:
    ts = pd.date_range("2026-01-05 10:00", periods=4, freq="min", tz="Asia/Kolkata").tz_convert("UTC")
    labels = pd.DataFrame(
        {
            "decision_timestamp": ts,
            "fwd_15m_status": ["MEASURED"] * 4,
            "fwd_15m_signed_points": [40.0, -35.0, 4.0, -3.0],
        }
    )
    predictions = pd.DataFrame(
        {
            "decision_timestamp": ts,
            "probability_up": [0.75, 0.20, 0.60, 0.45],
            "expected_signed_points": [32.0, -28.0, 5.0, -4.0],
        }
    )
    metrics = evaluate_direction_magnitude_forecasts(
        predictions,
        labels,
        horizon_minutes=15,
        min_probability_direction=0.70,
        min_abs_expected_move_points=20.0,
    )
    assert metrics["rows"] == 4
    assert metrics["direction_accuracy"] == 1.0
    assert metrics["selective_rows"] == 2
    assert metrics["selective_direction_accuracy"] == 1.0
    assert metrics["selective_mean_aligned_realized_points"] == 37.5
