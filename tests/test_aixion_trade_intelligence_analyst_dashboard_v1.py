from __future__ import annotations

import pytest

from aixion_trade_intelligence.analyst_workflow import (
    AnalystState,
    ControlledAnalystWorkflow,
    build_optional_langgraph_workflow,
)
from aixion_trade_intelligence.dashboard_read_model import build_dashboard_read_model


def test_controlled_analyst_accepts_only_cited_noncontradictory_claims():
    workflow = ControlledAnalystWorkflow(
        lambda metrics, evidence: [
            {
                "claim": "The session data is invalid because sequence coverage failed.",
                "claim_type": "FACT",
                "evidence_refs": ["report/session_analysis.json"],
            }
        ]
    )
    result = workflow.run(
        AnalystState(
            session_id="s1",
            deterministic_metrics={"valid": False, "ready_for_profitability_claim": False},
            retrieved_evidence=(
                {"source_path": "report/session_analysis.json", "verdict": "INVALID_SEQUENCE_COVERAGE"},
            ),
        )
    )
    assert result.verdict == "CITED_ANALYSIS_ACCEPTED"
    assert result.contradictions == ()
    assert result.claims[0].evidence_refs == ("report/session_analysis.json",)


def test_controlled_analyst_rejects_unknown_citation():
    workflow = ControlledAnalystWorkflow(
        lambda metrics, evidence: [
            {
                "claim": "Unsupported claim",
                "claim_type": "FACT",
                "evidence_refs": ["invented.json"],
            }
        ]
    )
    with pytest.raises(ValueError, match="unknown_evidence"):
        workflow.run(
            AnalystState(
                session_id="s1",
                deterministic_metrics={"valid": True},
                retrieved_evidence=({"source_path": "real.json"},),
            )
        )


def test_controlled_analyst_rejects_profitability_contradiction():
    workflow = ControlledAnalystWorkflow(
        lambda metrics, evidence: [
            {
                "claim": "Profitability certified and ready for live.",
                "claim_type": "SUPPORTED_INFERENCE",
                "evidence_refs": ["report.json"],
            }
        ]
    )
    result = workflow.run(
        AnalystState(
            session_id="s1",
            deterministic_metrics={"valid": True, "ready_for_profitability_claim": False},
            retrieved_evidence=({"source_path": "report.json"},),
        )
    )
    assert result.verdict == "REJECTED_CONTRADICTORY_ANALYSIS"
    assert result.contradictions == ("CLAIM_CONTRADICTS_PROFITABILITY_READINESS",)


def test_optional_langgraph_adapter_is_explicit_when_dependency_absent():
    try:
        graph = build_optional_langgraph_workflow(lambda metrics, evidence: ())
    except RuntimeError as exc:
        assert str(exc) == "langgraph_not_installed"
    else:
        assert graph is not None


def test_dashboard_read_model_preserves_certification_boundary():
    model = build_dashboard_read_model(
        {
            "manifest": {
                "session_id": "s1",
                "run_id": "r1",
                "verdict": "VALID_OFFLINE_SESSION_EVIDENCE",
                "valid": True,
                "first_event_time": "start",
                "last_event_time": "end",
                "event_count": 10,
                "instrument_count": 2,
                "invalid_quality_event_count": 0,
                "producer_sequence_gap_total": 0,
                "event_log_sha256": "abc",
            },
            "candidate_funnel": {"candidate_count": 1},
            "runtime_timeline": [{"event_type": "SESSION_STARTED"}],
            "outcome_readiness": {
                "ready_for_strategy_diagnosis": True,
                "ready_for_profitability_claim": False,
                "reason": "HOLDOUT_REQUIRED",
            },
        },
        certification={"verdict": "INSUFFICIENT_EVIDENCE"},
    )
    record = model.to_record()
    assert record["session"]["valid"] is True
    assert record["research_status"]["ready_for_profitability_claim"] is False
    assert record["research_status"]["certification_verdict"] == "INSUFFICIENT_EVIDENCE"
