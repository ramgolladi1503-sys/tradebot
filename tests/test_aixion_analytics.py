from __future__ import annotations

from dataclasses import replace

from scripts.generate_offline_fixture import build_fixture
from aixion_trade_intelligence.analytics import AVAILABLE, UNAVAILABLE, build_session_analytics
from aixion_trade_intelligence.lineage import build_candidate_lineage
from aixion_trade_intelligence.outcomes import calculate_outcomes
from aixion_trade_intelligence.replay import assert_replay_deterministic


def _analytics(events):
    ordered = assert_replay_deterministic(events).ordered_events
    lineage = build_candidate_lineage(ordered)
    outcomes = calculate_outcomes(ordered, lineage)
    return build_session_analytics(ordered, lineage, outcomes)


def test_session_analytics_derives_index_and_candidate_metrics_from_evidence():
    analytics = _analytics(build_fixture())
    by_id = {row.metric_id: row for row in analytics.metrics}
    assert by_id["index_path"].status == AVAILABLE
    assert by_id["index_path"].value["instrument_key"] == "NSE_INDEX|Nifty 50"
    assert by_id["candidate_liquidity:candidate-offline-001"].status == AVAILABLE
    assert by_id["candidate_timing:candidate-offline-001"].status == AVAILABLE
    assert by_id["futures_basis"].status == UNAVAILABLE
    assert by_id["constituent_breadth"].status == UNAVAILABLE


def test_declared_futures_basis_uses_only_causal_pairs():
    events = build_fixture()
    start = events[0]
    payload = dict(start.payload)
    payload["analytics_contract"] = {
        "index_instrument": "NSE_INDEX|Nifty 50",
        "futures_instrument": "NSE_FO|OFFLINE_ATM_CE",
        "max_pair_lag_seconds": 0.01,
        "required_metrics": ["index_path", "futures_basis"],
    }
    events[0] = replace(start, payload=payload, payload_hash="")
    analytics = _analytics(events)
    by_id = {row.metric_id: row for row in analytics.metrics}
    assert by_id["futures_basis"].status == AVAILABLE
    assert not analytics.missing_required_metrics


def test_required_metric_is_missing_when_dependency_contract_is_absent():
    events = build_fixture()
    start = events[0]
    payload = dict(start.payload)
    payload["analytics_contract"] = {
        "required_metrics": ["futures_basis"],
    }
    events[0] = replace(start, payload=payload, payload_hash="")
    analytics = _analytics(events)
    assert analytics.missing_required_metrics == ("futures_basis",)
