from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from scripts.generate_offline_fixture import build_fixture
from aixion_trade_intelligence.certification import PIPELINE_CERTIFIED, PIPELINE_REJECTED, certify_session


def test_offline_pipeline_certifies_but_edge_does_not():
    result = certify_session(build_fixture())
    assert result.verdict == PIPELINE_CERTIFIED
    assert result.pipeline_certified is True
    assert result.strategy_edge_certified is False
    assert result.lineage_count == 1
    assert result.outcome_count == 3
    assert all(check.passed for check in result.checks)


def test_leakage_rejects_certification():
    events = build_fixture()
    for idx, event in enumerate(events):
        if event.event_type == "STRATEGY_EVALUATED":
            payload = dict(event.payload)
            payload["feature_available_times"] = {
                "future": (event.event_time + timedelta(seconds=2)).isoformat()
            }
            events[idx] = replace(event, payload=payload, payload_hash="")
            break
    result = certify_session(events)
    assert result.verdict == PIPELINE_REJECTED
    checks = {check.check_id: check.passed for check in result.checks}
    assert checks["NO_LOOKAHEAD"] is False


def test_candidate_without_outcome_contract_rejects_full_pipeline_certification():
    events = build_fixture()
    for idx, event in enumerate(events):
        if event.candidate_id == "candidate-offline-001" and event.event_type in {
            "STRATEGY_EVALUATED", "SIGNAL_GENERATED", "CANDIDATE_CREATED"
        }:
            payload = dict(event.payload)
            payload.pop("outcome_contract", None)
            events[idx] = replace(event, payload=payload, payload_hash="")
    result = certify_session(events)
    assert result.verdict == PIPELINE_REJECTED
    checks = {check.check_id: check.passed for check in result.checks}
    assert checks["CANDIDATE_OUTCOME_CONTRACT_COVERAGE"] is False


def test_missing_executable_outcome_evidence_rejects_certification():
    events = build_fixture()
    trimmed = [
        event
        for event in events
        if not (
            event.event_type == "MARKET_QUOTE"
            and event.instrument_key == "NSE_FO|OFFLINE_ATM_CE"
            and event.event_time >= events[0].event_time + timedelta(seconds=300)
        )
    ]
    from dataclasses import replace
    for index, event in enumerate(trimmed):
        if event.event_type == "SESSION_ENDED":
            payload = dict(event.payload)
            payload["expected_producer_counts"] = {"offline-fixture": len(trimmed)}
            trimmed[index] = replace(event, payload=payload, payload_hash="")
            break
    result = certify_session(trimmed)
    assert result.verdict == PIPELINE_REJECTED
    checks = {check.check_id: check.passed for check in result.checks}
    assert checks["OUTCOME_EVIDENCE_COMPLETE"] is False


def test_malformed_outcome_contract_is_rejected_without_crashing():
    events = build_fixture()
    for idx, event in enumerate(events):
        if event.candidate_id == "candidate-offline-001" and event.event_type in {
            "STRATEGY_EVALUATED", "SIGNAL_GENERATED", "CANDIDATE_CREATED"
        }:
            payload = dict(event.payload)
            payload["outcome_contract"] = {
                "horizons_seconds": [],
                "underlying_instrument": "NSE_INDEX|Nifty 50",
                "selected_option_instrument": "NSE_FO|OFFLINE_ATM_CE",
            }
            events[idx] = replace(event, payload=payload, payload_hash="")
    result = certify_session(events)
    assert result.verdict == PIPELINE_REJECTED
    assert "outcomes" in result.analysis_errors
    checks = {check.check_id: check.passed for check in result.checks}
    assert checks["OUTCOME_CALCULATION_VALID"] is False


def test_declared_missing_analytics_rejects_certification():
    events = build_fixture()
    start = events[0]
    payload = dict(start.payload)
    payload["analytics_contract"] = {"required_metrics": ["futures_basis"]}
    events[0] = replace(start, payload=payload, payload_hash="")
    result = certify_session(events)
    assert result.verdict == PIPELINE_REJECTED
    checks = {check.check_id: check.passed for check in result.checks}
    assert checks["DECLARED_ANALYTICS_COMPLETE"] is False
