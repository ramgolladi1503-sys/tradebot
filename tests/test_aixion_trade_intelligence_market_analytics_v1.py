from __future__ import annotations

import pytest

from aixion_trade_intelligence.market_analytics import (
    BookLevel,
    calculate_breadth,
    calculate_futures_basis,
    calculate_option_microstructure,
    lead_lag_returns,
)


def test_breadth_calculates_weighted_participation_and_concentration():
    result = calculate_breadth(
        {"A": 0.01, "B": -0.02, "C": 0.03, "D": 0.0},
        weights={"A": 0.4, "B": 0.3, "C": 0.2, "D": 0.1},
    )
    assert result.constituent_count == 4
    assert (result.positive_count, result.negative_count, result.unchanged_count) == (2, 1, 1)
    assert result.equal_weight_breadth == pytest.approx(0.25)
    assert result.weighted_breadth == pytest.approx(0.3)
    assert result.absolute_contribution == pytest.approx(0.016)
    assert result.top3_concentration == pytest.approx(1.0)


def test_breadth_refuses_incomplete_point_in_time_weights():
    with pytest.raises(ValueError, match="missing_weights=B"):
        calculate_breadth({"A": 0.01, "B": 0.02}, weights={"A": 1.0})


def test_futures_basis_derives_relative_change_without_thresholds():
    result = calculate_futures_basis(
        index_price=100.0,
        futures_price=101.0,
        previous_index_price=99.0,
        previous_futures_price=99.5,
    )
    assert result.basis == pytest.approx(1.0)
    assert result.basis_pct == pytest.approx(0.01)
    assert result.basis_change == pytest.approx(0.5)
    assert result.futures_return_minus_index_return == pytest.approx(
        (101.0 / 99.5 - 1.0) - (100.0 / 99.0 - 1.0)
    )


def test_option_microstructure_uses_observed_book_quantities():
    result = calculate_option_microstructure(
        bid=99.0,
        ask=101.0,
        bid_levels=(BookLevel(99.0, 120), BookLevel(98.5, 80)),
        ask_levels=(BookLevel(101.0, 40), BookLevel(101.5, 60)),
    )
    assert result.mid == pytest.approx(100.0)
    assert result.spread_pct_mid == pytest.approx(0.02)
    assert result.top_depth_imbalance == pytest.approx(0.5)
    assert result.microprice == pytest.approx(100.5)
    assert result.full_depth_imbalance == pytest.approx(1.0 / 3.0)


def test_option_microstructure_rejects_crossed_quotes():
    with pytest.raises(ValueError, match="crossed_quote"):
        calculate_option_microstructure(bid=102.0, ask=101.0)


def test_lead_lag_returns_matches_only_information_available_before_cutoff():
    result = lead_lag_returns(
        [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)],
        [(2.0, 10.0), (3.0, 20.0), (4.0, 30.0)],
        lags_seconds=(1.0,),
    )
    assert result[1.0] == pytest.approx(1.0)
