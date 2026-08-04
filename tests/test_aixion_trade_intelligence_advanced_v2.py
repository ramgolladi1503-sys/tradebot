from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from aixion_trade_intelligence.agent_workflow import run_controlled_review
from aixion_trade_intelligence.campaign import SessionEvidence, summarize_campaign
from aixion_trade_intelligence.capacity import (
    MarketImpactObservation,
    QueueObservation,
    build_capacity_curve,
    calibrate_queue_fill_probability,
    fit_sqrt_impact_model,
)
from aixion_trade_intelligence.cas import CASSessionObservation, summarize_cas_campaign
from aixion_trade_intelligence.costs import CostSchedule, TradeCostInput, calculate_trade_costs
from aixion_trade_intelligence.counterfactuals import ContractOutcome, blocker_value, compare_contract_counterfactuals
from aixion_trade_intelligence.drift import diagonal_zscore_ood, jensen_shannon_divergence, ks_statistic, population_stability_index
from aixion_trade_intelligence.event_graph import MarketEventNode, build_market_event_graph
from aixion_trade_intelligence.feature_parity import FeatureRecord, compare_feature_modes, hash_feature_inputs
from aixion_trade_intelligence.greek_attribution import GreekSnapshot, attribute_option_pnl
from aixion_trade_intelligence.market_analytics import BookLevel, calculate_breadth, calculate_futures_basis, calculate_option_microstructure, lead_lag_returns
from aixion_trade_intelligence.rag_ingestion import ingest_evidence_file, plan_evidence_query
from aixion_trade_intelligence.risk_analytics import block_bootstrap_risk
from aixion_trade_intelligence.validation import LabelInterval, compare_to_baseline, deflated_sharpe_ratio, probability_of_backtest_overfitting, purged_embargoed_splits


UTC = timezone.utc
BASE = datetime(2026, 8, 5, 3, 45, tzinfo=UTC)


def test_market_structure_metrics_are_derived() -> None:
    breadth = calculate_breadth({"A": 0.01, "B": 0.02, "C": -0.01, "D": 0.0}, weights={"A": 0.4, "B": 0.3, "C": 0.2, "D": 0.1})
    assert breadth.equal_weight_breadth == pytest.approx(0.25)
    assert breadth.weighted_breadth == pytest.approx(0.5)
    basis = calculate_futures_basis(index_price=25000, futures_price=25020, previous_index_price=24900, previous_futures_price=24910)
    assert basis.basis_change == pytest.approx(10)
    micro = calculate_option_microstructure(bid=99, ask=101, bid_levels=(BookLevel(99, 100),), ask_levels=(BookLevel(101, 50),))
    assert micro.microprice == pytest.approx((101 * 100 + 99 * 50) / 150)
    assert lead_lag_returns([(1, 1), (2, 2), (3, 3)], [(2, 1), (3, 2), (4, 3)], lags_seconds=[1])[1.0] == pytest.approx(1)


def test_effective_dated_costs_and_greek_attribution() -> None:
    schedule = CostSchedule.from_mapping({"schedule_id": "OPTIONS", "version": "v1", "effective_from": "2026-08-01", "rules": [{"name": "brokerage", "kind": "FLAT_PER_ORDER", "side": "BOTH", "base": "TOTAL_TURNOVER", "value": 20}, {"name": "exchange", "kind": "RATE", "side": "BOTH", "base": "TOTAL_TURNOVER", "value": 0.001}, {"name": "tax", "kind": "RATE", "side": "BOTH", "base": "ACCUMULATED_COMPONENTS", "component_names": ["brokerage", "exchange"], "value": 0.18}]})
    result = calculate_trade_costs(schedule, TradeCostInput(date(2026, 8, 5), 10000, 11000, 1, 1))
    assert result.total_cost == pytest.approx(71.98)
    attribution = attribute_option_pnl(start=GreekSnapshot(100, 25000, 15, 0.5, 0.002, -2, 1.5), end_option_price=112, end_underlying_price=25020, end_implied_volatility_points=16, elapsed_days=0.1, quantity=65)
    components = attribution.delta_contribution + attribution.gamma_contribution + attribution.theta_contribution + attribution.vega_contribution + attribution.explicit_other_contribution + attribution.residual_contribution
    assert components == pytest.approx(attribution.observed_pnl)


def test_capacity_queue_and_impact_are_observation_driven() -> None:
    curve = build_capacity_curve((BookLevel(100, 50), BookLevel(101, 50), BookLevel(102, 100)), quantities=[50, 100, 150], side="BUY")
    assert curve[1].vwap == pytest.approx(100.5)
    buckets = calibrate_queue_fill_probability([QueueObservation(100, 50, 0, False), QueueObservation(100, 120, 0, True), QueueObservation(100, 150, 0, True)], bucket_edges=[0, 1, 2], confidence=0.95)
    assert sum(item.observations for item in buckets) == 3
    model = fit_sqrt_impact_model([MarketImpactObservation(0.01, 2), MarketImpactObservation(0.04, 4), MarketImpactObservation(0.09, 6)])
    assert model.coefficient == pytest.approx(20)


def test_counterfactuals_and_blocker_value() -> None:
    comparison = compare_contract_counterfactuals([ContractOutcome("c", "ATM", "SELECTED", 100, 10, 65, 65, "atm.json"), ContractOutcome("c", "ITM", "ALTERNATIVE", 150, 15, 65, 65, "itm.json")], selected_contract_id="ATM", candidate_was_rejected=False)
    assert comparison.selected_opportunity_cost == pytest.approx(45)
    values = blocker_value([{"blocker": "STALE", "was_blocked": True, "counterfactual_net_pnl": -50}, {"blocker": "STALE", "was_blocked": True, "counterfactual_net_pnl": 30}])
    assert values["STALE"]["net_value_of_blocker"] == pytest.approx(20)


def test_feature_parity_and_research_integrity() -> None:
    digest = hash_feature_inputs({"price": 100})
    live = FeatureRecord("NIFTY", "breadth", "1", "LIVE", BASE, BASE - timedelta(milliseconds=1), digest, {"value": 0.5})
    replay = FeatureRecord("NIFTY", "breadth", "1", "REPLAY", BASE, BASE - timedelta(milliseconds=1), digest, {"value": 0.5})
    assert compare_feature_modes([live], [replay]).valid
    intervals = [LabelInterval(f"s{i}", BASE + timedelta(minutes=i), BASE + timedelta(minutes=i + 2)) for i in range(8)]
    splits = purged_embargoed_splits(intervals, n_splits=4, embargo=timedelta(minutes=1))
    assert any(split.purged_ids for split in splits)
    assert 0 <= deflated_sharpe_ratio(observed_sharpe=1.2, observations=100, skewness=0, kurtosis=3, trials=10, trial_sharpe_std=0.2)["probability"] <= 1
    pbo = probability_of_backtest_overfitting([[0.01, -0.01, 0.005], [0.02, -0.02, 0.004], [-0.01, 0.01, 0.003], [0.03, -0.01, -0.002], [-0.02, 0.02, 0.001], [0.01, -0.01, 0.002]], partitions=2, metric="MEAN")
    assert 0 <= pbo["probability_of_backtest_overfitting"] <= 1
    assert compare_to_baseline([0.02, 0.01], [0.01, 0])["mean_incremental_return"] == pytest.approx(0.01)


def test_drift_ood_and_seeded_risk() -> None:
    assert population_stability_index([0, 0, 1, 1], [0, 1, 2, 2], bin_edges=[0, 1, 2, 3], smoothing=0.5) >= 0
    assert ks_statistic([0, 0, 1, 1], [0, 1, 2, 2]) >= 0
    assert jensen_shannon_divergence([0, 0, 1, 1], [0, 1, 2, 2], bin_edges=[0, 1, 2, 3], smoothing=0.5) >= 0
    assert diagonal_zscore_ood({"a": 2, "b": 4}, reference_means={"a": 1, "b": 2}, reference_stddevs={"a": 1, "b": 2}).squared_distance == pytest.approx(2)
    kwargs = dict(initial_capital=100000, block_length=2, periods_per_path=10, paths=100, ruin_fraction=0.5, drawdown_thresholds=[0.1, 0.2], seed=7)
    assert block_bootstrap_risk([0.01, -0.02, 0.015, -0.005], **kwargs) == block_bootstrap_risk([0.01, -0.02, 0.015, -0.005], **kwargs)


def test_cas_graph_rag_agent_and_campaign(tmp_path) -> None:
    cas = summarize_cas_campaign([CASSessionObservation(date(2026, 8, 3), "s1", False, 24575.1, 24774.3, 0.9, 0.15, 5, 30, "VALID", "s1.json"), CASSessionObservation(date(2026, 8, 4), "s2", True, 24465.05, 24614.9, 0.94, 0.2, 4, 20, "VALID", "s2.json")], accepted_quality_states={"VALID"}, minimum_expiry_sessions=1, minimum_non_expiry_sessions=1)
    assert cas.ready_for_directional_testing
    graph = build_market_event_graph([MarketEventNode("a", "BREADTH", BASE, BASE, (), "a.json"), MarketEventNode("b", "INDEX", BASE + timedelta(seconds=2), BASE + timedelta(seconds=1), ("a",), "b.json")])
    assert graph.topological_order == ("a", "b")
    report = tmp_path / "report.md"
    report.write_text("# Session\nFeed stale and candidate blocked.", encoding="utf-8")
    assert ingest_evidence_file(report, document_type="SESSION_REPORT", max_characters_per_chunk=50)
    assert plan_evidence_query("What was average latency?") == "STRUCTURED_ANALYTICS"
    review = run_controlled_review(deterministic_metrics={"verdict": "INSUFFICIENT_EVIDENCE"}, evidence=[{"source_path": "report.json", "content_hash": "abc", "content": "insufficient", "metadata": {}}], analyst=lambda **_: {"claim": "profitable"}, critic=lambda **_: {"unsupported_claims": ["profitable"], "contradictions": [], "fact_inference_boundary": {}})
    assert review.final["status"] == "REVIEW_REJECTED"
    reports = []
    for index, expiry in enumerate((True, False)):
        path = tmp_path / f"{index}.json"
        path.write_text(json.dumps({"manifest": {"session_id": f"s{index}", "verdict": "VALID_OFFLINE_SESSION_EVIDENCE", "valid": True}, "outcome_readiness": {"ready_for_strategy_diagnosis": True}, "metadata": {"expiry_session": expiry, "live_shadow_consistent": True}}), encoding="utf-8")
        reports.append(SessionEvidence.from_report(path))
    summary = summarize_campaign(reports, minimum_valid_sessions=2, minimum_expiry_sessions=1, minimum_non_expiry_sessions=1, require_all_diagnosis_ready=True, require_live_shadow_for_all_valid=True)
    assert summary.ready_for_multi_session_review
