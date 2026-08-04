from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from aixion_trade_intelligence.capacity import (
    MarketImpactObservation,
    QueueObservation,
    build_capacity_curve,
    calibrate_queue_fill_probability,
    fit_sqrt_impact_model,
)
from aixion_trade_intelligence.cas_accumulator import (
    CASObservation,
    CASPhase,
    aggregate_cas_sessions,
    assign_phase,
    summarize_cas_session,
)
from aixion_trade_intelligence.costs import (
    CostSchedule,
    TradeCostInput,
    calculate_trade_costs,
)
from aixion_trade_intelligence.drift import (
    diagonal_zscore_ood,
    jensen_shannon_divergence,
    ks_statistic,
    population_stability_index,
)
from aixion_trade_intelligence.feature_parity import (
    FeatureRecord,
    compare_feature_modes,
    hash_feature_inputs,
)
from aixion_trade_intelligence.greek_attribution import GreekSnapshot, attribute_option_pnl
from aixion_trade_intelligence.market_analytics import BookLevel
from aixion_trade_intelligence.market_event_graph import (
    MarketEvent,
    event_path,
    validate_market_event_graph,
)
from aixion_trade_intelligence.risk_simulation import block_bootstrap_risk


BASE = datetime(2026, 8, 5, 9, 15, tzinfo=timezone.utc)


def test_effective_dated_cost_rules_are_external_and_dependency_ordered():
    schedule = CostSchedule.from_mapping(
        {
            "schedule_id": "fixture",
            "version": "1",
            "effective_from": "2026-01-01",
            "rules": [
                {"name": "brokerage", "kind": "FLAT_PER_ORDER", "side": "BOTH", "base": "BROKERAGE", "value": 20.0},
                {"name": "exchange", "kind": "RATE", "side": "BOTH", "base": "TOTAL_TURNOVER", "value": 0.001},
                {"name": "tax", "kind": "RATE", "side": "BOTH", "base": "ACCUMULATED_COMPONENTS", "value": 0.18, "component_names": ["brokerage", "exchange"]},
            ],
        }
    )
    result = calculate_trade_costs(
        schedule,
        TradeCostInput(date(2026, 8, 5), 10000.0, 12000.0, 1, 1),
    )
    assert result.components == {"brokerage": 40.0, "exchange": 22.0, "tax": 11.16}
    assert result.total_cost == pytest.approx(73.16)


def test_greek_attribution_reconciles_observed_pnl_to_residual():
    result = attribute_option_pnl(
        start=GreekSnapshot(100.0, 1000.0, 20.0, 0.5, 0.01, -2.0, 1.5),
        end_option_price=108.0,
        end_underlying_price=1010.0,
        end_implied_volatility_points=21.0,
        elapsed_days=0.5,
        quantity=2,
    )
    explained = (
        result.delta_contribution
        + result.gamma_contribution
        + result.theta_contribution
        + result.vega_contribution
        + result.explicit_other_contribution
        + result.residual_contribution
    )
    assert explained == pytest.approx(result.observed_pnl)


def test_capacity_curve_and_calibrated_queue_model_use_observations():
    curve = build_capacity_curve(
        (BookLevel(101.0, 10), BookLevel(102.0, 20)),
        quantities=(5.0, 15.0, 40.0),
        side="BUY",
    )
    assert curve[0].vwap == pytest.approx(101.0)
    assert curve[1].vwap == pytest.approx((10 * 101 + 5 * 102) / 15)
    assert curve[2].fully_filled is False
    buckets = calibrate_queue_fill_probability(
        (
            QueueObservation(100, 50, 0, False),
            QueueObservation(100, 110, 0, True),
            QueueObservation(100, 120, 0, True),
        ),
        bucket_edges=(0.0, 1.0, 2.0),
        confidence=0.95,
    )
    assert buckets[0].fill_probability == 0.0
    assert buckets[1].fill_probability == 1.0
    impact = fit_sqrt_impact_model(
        (MarketImpactObservation(0.01, 1.0), MarketImpactObservation(0.04, 2.0))
    )
    assert impact.coefficient == pytest.approx(10.0)


def test_feature_parity_detects_cross_mode_output_mismatch():
    input_hash = hash_feature_inputs({"price": 100.0})
    live = FeatureRecord("NIFTY", "breadth", "1", "LIVE", BASE, BASE, input_hash, {"value": 0.2})
    replay = FeatureRecord("NIFTY", "breadth", "1", "REPLAY", BASE, BASE, input_hash, {"value": 0.3})
    report = compare_feature_modes((live,), (replay,))
    assert report.valid is False
    assert report.output_hash_mismatches == (live.parity_key,)


def test_drift_metrics_and_ood_are_numeric_not_policy_thresholds():
    psi = population_stability_index([0.0, 0.1, 0.2], [0.8, 0.9, 1.0], bin_edges=(0.0, 0.5, 1.0), smoothing=0.5)
    js = jensen_shannon_divergence([0.0, 0.1, 0.2], [0.8, 0.9, 1.0], bin_edges=(0.0, 0.5, 1.0), smoothing=0.5)
    ks = ks_statistic([0.0, 0.1, 0.2], [0.8, 0.9, 1.0])
    ood = diagonal_zscore_ood({"x": 2.0}, reference_means={"x": 0.0}, reference_stddevs={"x": 1.0})
    assert psi > 0
    assert js > 0
    assert ks == 1.0
    assert ood.squared_distance == 4.0


def test_block_bootstrap_risk_is_seed_reproducible():
    arguments = dict(
        session_returns=(0.01, -0.02, 0.015, -0.01, 0.005),
        initial_equity=100000.0,
        ruin_equity=70000.0,
        periods=20,
        paths=100,
        block_length=2,
        seed=7,
    )
    first = block_bootstrap_risk(**arguments)
    second = block_bootstrap_risk(**arguments)
    assert first == second
    assert 0.0 <= first.ruin_fraction <= 1.0


def test_cas_accumulator_separates_configured_phases_and_expiry_classes():
    phases = (
        CASPhase("PRE", time(15, 0), time(15, 15)),
        CASPhase("DISCOVERY", time(15, 15), time(15, 30)),
    )
    local_tz = timezone(timedelta(hours=5, minutes=30))
    first_time = datetime(2026, 8, 5, 15, 14, tzinfo=local_tz)
    second_time = datetime(2026, 8, 5, 15, 20, tzinfo=local_tz)
    rows = (
        CASObservation("s1", first_time, 100.0, assign_phase(first_time, phases), "NON_EXPIRY"),
        CASObservation("s1", second_time, 101.0, assign_phase(second_time, phases), "NON_EXPIRY"),
    )
    summary = summarize_cas_session(rows, pre_transition_phase="PRE")
    aggregate = aggregate_cas_sessions((summary,))
    assert summary.change_points == pytest.approx(1.0)
    assert aggregate["NON_EXPIRY"]["sessions"] == 1


def test_market_event_graph_rejects_future_parent_and_traces_valid_path():
    parent = MarketEvent("a", "BREADTH", BASE, BASE, "UP", 1.0, (), {})
    child = MarketEvent("b", "INDEX", BASE + timedelta(seconds=1), BASE + timedelta(seconds=1), "UP", 1.0, ("a",), {})
    valid = validate_market_event_graph((parent, child))
    assert valid.valid is True
    assert event_path((parent, child), target_event_id="b") == ("a", "b")
    future_parent = MarketEvent("c", "FUTURE", BASE + timedelta(seconds=2), BASE + timedelta(seconds=2), "UP", 1.0, (), {})
    invalid_child = MarketEvent("d", "OPTION", BASE + timedelta(seconds=1), BASE + timedelta(seconds=1), "UP", 1.0, ("c",), {})
    invalid = validate_market_event_graph((future_parent, invalid_child))
    assert invalid.valid is False
    assert invalid.future_parent_edges == (("c", "d"),)
