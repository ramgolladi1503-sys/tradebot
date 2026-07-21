import math

import pandas as pd

from research.rsi2_mean_reversion.engine import (
    BASE_COST,
    NEXT_OPEN,
    SIMPLE_RSI_2,
    WILDER_RSI_2,
    build_trade_ledger,
    independent_wilder_oracle,
    prepare_features,
    simple_rsi,
    wilder_rsi,
)
from research.rsi2_mean_reversion.evidence_closure import semantic_hash
from research.rsi2_mean_reversion.publication_gate import (
    ALLOWED_VERDICTS,
    REQUIRED_CONTROLS,
    control_completeness,
    matched_random_replicates,
    parameter_neighborhood,
    verdict_decision_table,
)


def test_simple_rsi_two_period_hand_calculated_values():
    close = pd.Series([100.0, 101.0, 100.0, 102.0, 101.0])

    values = simple_rsi(close, period=2)

    assert math.isclose(values.iloc[2], 50.0, abs_tol=1e-12)
    assert math.isclose(values.iloc[3], 66.6666666667, rel_tol=1e-9)
    assert math.isclose(values.iloc[4], 66.6666666667, rel_tol=1e-9)


def test_wilder_rsi_matches_independent_oracle():
    close = pd.Series([100.0, 101.0, 100.0, 102.0, 101.0, 104.0, 103.0])

    implementation = wilder_rsi(close, period=2)
    oracle = independent_wilder_oracle(close.tolist(), period=2)

    for got, expected in zip(implementation.tolist(), oracle, strict=True):
        if expected is None:
            assert pd.isna(got)
        else:
            assert math.isclose(got, expected, rel_tol=1e-12)


def test_next_open_ledger_uses_session_after_completed_signal():
    dates = pd.date_range("2020-01-01", periods=8, freq="B")
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": [100.0, 99.0, 98.0, 97.0, 100.0, 103.0, 104.0, 105.0],
            "high": [101.0, 100.0, 99.0, 101.0, 104.0, 105.0, 106.0, 107.0],
            "low": [99.0, 97.0, 96.0, 95.0, 99.0, 102.0, 103.0, 104.0],
            "close": [100.0, 99.0, 98.0, 97.0, 103.0, 104.0, 105.0, 106.0],
        }
    )
    featured = prepare_features(frame, SIMPLE_RSI_2, 2, 2)

    ledger, _ = build_trade_ledger(
        featured,
        lane=NEXT_OPEN,
        rsi_variant=WILDER_RSI_2,
        entry_threshold=15.0,
        exit_threshold=85.0,
        sma_period=2,
        use_trend_filter=False,
        cost=BASE_COST,
    )

    assert len(ledger) == 1
    assert ledger.iloc[0]["signal_timestamp"] == "2020-01-03"
    assert ledger.iloc[0]["entry_timestamp"] == "2020-01-06"
    assert ledger.iloc[0]["entry_price"] == 97.0
    assert ledger.iloc[0]["exit_timestamp"] == "2020-01-08"


def test_rsi_edge_cases_are_deterministic():
    all_gain = pd.Series([1.0, 2.0, 3.0, 4.0])
    all_loss = pd.Series([4.0, 3.0, 2.0, 1.0])
    flat = pd.Series([2.0, 2.0, 2.0, 2.0])

    assert simple_rsi(all_gain, 2).iloc[-1] == 100.0
    assert simple_rsi(all_loss, 2).iloc[-1] == 0.0
    assert simple_rsi(flat, 2).iloc[-1] == 50.0
    assert wilder_rsi(all_gain, 2).iloc[-1] == 100.0
    assert wilder_rsi(all_loss, 2).iloc[-1] == 0.0
    assert wilder_rsi(flat, 2).iloc[-1] == 50.0
    assert pd.isna(wilder_rsi(all_gain, 2).iloc[1])


def test_no_same_bar_fill_and_open_position_excluded():
    dates = pd.date_range("2020-01-01", periods=5, freq="B")
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": [10, 9, 8, 7, 6],
            "high": [11, 10, 9, 8, 7],
            "low": [9, 8, 7, 6, 5],
            "close": [10, 9, 8, 7, 6],
        }
    )
    featured = prepare_features(frame, SIMPLE_RSI_2, 2, 2)
    ledger, _ = build_trade_ledger(
        featured,
        lane=NEXT_OPEN,
        rsi_variant=SIMPLE_RSI_2,
        entry_threshold=15.0,
        exit_threshold=85.0,
        sma_period=2,
        use_trend_filter=False,
        cost=BASE_COST,
    )

    assert ledger.empty


def test_cost_applied_once_and_ledger_reconciles_equity_without_overlap():
    dates = pd.date_range("2020-01-01", periods=8, freq="B")
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": [100, 99, 98, 97, 100, 103, 102, 105],
            "high": [101, 100, 99, 101, 104, 105, 103, 106],
            "low": [99, 97, 96, 95, 99, 101, 101, 104],
            "close": [100, 99, 98, 97, 103, 104, 102, 106],
        }
    )
    featured = prepare_features(frame, SIMPLE_RSI_2, 2, 2)
    ledger, equity = build_trade_ledger(
        featured,
        lane=NEXT_OPEN,
        rsi_variant=SIMPLE_RSI_2,
        entry_threshold=15.0,
        exit_threshold=85.0,
        sma_period=2,
        use_trend_filter=False,
        cost=BASE_COST,
    )

    row = ledger.iloc[0]
    expected_net = row["gross_return"] - BASE_COST.total_bps / 10000.0
    assert math.isclose(row["net_return"], expected_net, rel_tol=1e-12)
    assert math.isclose((1.0 + ledger["net_return"]).prod(), equity.iloc[-1], rel_tol=1e-12)
    intervals = [
        (pd.Timestamp(r.entry_timestamp), pd.Timestamp(r.exit_timestamp))
        for r in ledger.itertuples()
    ]
    assert all(intervals[i][1] <= intervals[i + 1][0] for i in range(len(intervals) - 1))


def test_feature_generation_does_not_depend_on_future_mutation_before_signal_date():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=10, freq="B"),
            "open": [100, 101, 100, 99, 98, 99, 100, 101, 102, 103],
            "high": [101, 102, 101, 100, 99, 100, 101, 102, 103, 104],
            "low": [99, 100, 99, 98, 97, 98, 99, 100, 101, 102],
            "close": [100, 101, 100, 99, 98, 99, 100, 101, 102, 103],
        }
    )
    base = prepare_features(frame, WILDER_RSI_2, 2, 3)
    mutated = frame.copy()
    mutated.loc[9, "close"] = 10000
    changed = prepare_features(mutated, WILDER_RSI_2, 2, 3)

    pd.testing.assert_series_equal(base.loc[:7, "rsi"], changed.loc[:7, "rsi"])
    pd.testing.assert_series_equal(base.loc[:7, "sma"], changed.loc[:7, "sma"])


def test_parameter_combination_ids_cover_full_grid_deterministically():
    ids = {
        semantic_hash({"sma": sma, "entry": entry, "exit": exit_, "rsi_type": rsi_type, "lane": lane})
        for sma in [150, 200, 250]
        for entry in [5.0, 10.0, 15.0, 20.0]
        for exit_ in [70.0, 80.0, 85.0, 90.0]
        for rsi_type in ["WILDER_RSI_2", "SIMPLE_RSI_2"]
        for lane in ["NEXT_OPEN_EXECUTABLE", "SAME_CLOSE_THEORETICAL_PROXY"]
    }

    assert len(ids) == 192
    assert ids == {
        semantic_hash({"sma": sma, "entry": entry, "exit": exit_, "rsi_type": rsi_type, "lane": lane})
        for sma in [150, 200, 250]
        for entry in [5.0, 10.0, 15.0, 20.0]
        for exit_ in [70.0, 80.0, 85.0, 90.0]
        for rsi_type in ["WILDER_RSI_2", "SIMPLE_RSI_2"]
        for lane in ["NEXT_OPEN_EXECUTABLE", "SAME_CLOSE_THEORETICAL_PROXY"]
    }


def test_matched_random_replicates_exact_count_and_deterministic():
    _, first, first_summary = matched_random_replicates(replicates=5, seed=20260721)
    _, second, second_summary = matched_random_replicates(replicates=5, seed=20260721)

    assert first["completed_trades"].eq(127).all()
    assert first["overlap_count"].eq(0).all()
    assert (~first["duplicate_entries"]).all()
    pd.testing.assert_frame_equal(first, second)
    assert first_summary["empirical_p_value"] == second_summary["empirical_p_value"]


def test_verdict_fields_are_distinct_allowed_enums_and_deterministic():
    _, matched, summary = matched_random_replicates(replicates=5, seed=20260721)
    neighborhood, neighborhood_summary = parameter_neighborhood()
    base = pd.read_csv("runtime/research/rsi2_mean_reversion/completed_trade_ledger.csv")
    base = base[base["rsi_variant"] == "WILDER_RSI_2"].copy()

    verdict = verdict_decision_table(summary, neighborhood_summary, base)
    repeat = verdict_decision_table(summary, neighborhood_summary, base)

    assert verdict == repeat
    assert verdict["index_signal_verdict"] in ALLOWED_VERDICTS
    assert verdict["tradable_instrument_verdict"] in ALLOWED_VERDICTS
    assert verdict["overall_research_verdict"] in ALLOWED_VERDICTS
    assert verdict["index_signal_verdict"] != "INSUFFICIENT_TRADABLE_DATA"


def test_control_completeness_matrix_has_every_required_control():
    _, _, summary = matched_random_replicates(replicates=5, seed=20260721)
    rows = control_completeness(summary)

    assert {row["control_id"] for row in rows} == set(REQUIRED_CONTROLS)
    assert all(row["pass"] for row in rows)


def test_parameter_neighborhood_aggregation_recalculates_from_matrix():
    matrix, summary = parameter_neighborhood()

    assert len(matrix) == 27
    assert summary["positive_net_expectancy_pct"] == (matrix["expectancy"] > 0.0).mean() * 100.0
    assert summary["surviving_2x_costs_pct"] == (matrix["cost_2x_expectancy"] > 0.0).mean() * 100.0
