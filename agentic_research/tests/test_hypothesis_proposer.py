from agentic_research.contracts import CriticFinding, CriticReport, ToolResult
from agentic_research.hypotheses import BoundedHypothesisProposer


def test_proposer_creates_bounded_economic_hypothesis_for_oos_failure():
    report = CriticReport(
        critic_id="critic",
        findings=[CriticFinding(code="holdout_expectancy_non_positive", severity="BLOCKER", category="OVERFIT", message="holdout failed")],
    )
    results = {"run_adversarial_review": ToolResult(tool="run_adversarial_review", status="SUCCESS", payload={"report": report.model_dump(mode="json")}).with_hash()}
    proposals = BoundedHypothesisProposer().propose("trend_pullback_v1", "hash", results)
    assert len(proposals) == 1
    assert proposals[0].changed_fields == ["directional_regime_gate"]
    assert "Reject if" in proposals[0].rejection_condition


def test_proposer_does_not_tune_around_data_or_execution_blocker():
    report = CriticReport(
        critic_id="critic",
        findings=[
            CriticFinding(code="legacy_dataset_zero_volume", severity="BLOCKER", category="DATA", message="bad data"),
            CriticFinding(code="option_execution_not_certified", severity="BLOCKER", category="EXECUTION", message="not executable"),
        ],
    )
    result = ToolResult(tool="run_adversarial_review", status="SUCCESS", payload={"report": report.model_dump(mode="json")})
    assert BoundedHypothesisProposer().propose("trend_pullback_v1", "hash", {"run_adversarial_review": result}) == []
