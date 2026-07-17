from agentic_research.certification import DeterministicCertificationJudge
from agentic_research.contracts import CriticFinding, CriticReport, ToolResult


def r(name, payload=None, status="SUCCESS", blockers=None):
    return ToolResult(tool=name, status=status, payload=payload or {}, blockers=blockers or []).with_hash()


def gates():
    return {
        "minimum_total_trades": 2,
        "minimum_oos_trades": 1,
        "minimum_oos_net_expectancy_bps": 0,
        "minimum_oos_profit_factor": 1,
        "minimum_positive_oos_partition_fraction": 0.5,
        "maximum_causality_violations": 0,
        "promotion_ceiling": "READY_FOR_OPTION_REPLAY",
    }


def test_legacy_report_failure_is_authoritative():
    results = {
        "get_strategy_contract": r("get_strategy_contract"),
        "audit_existing_research_report": r("audit_existing_research_report", status="REJECTED", blockers=["legacy_dataset_zero_volume"]),
    }
    assert DeterministicCertificationJudge(gates()).decide(results).verdict == "REJECTED_DATA_INELIGIBLE"


def test_critic_can_block_apparently_positive_structural_result():
    report = CriticReport(
        critic_id="critic",
        findings=[CriticFinding(code="option_execution_not_certified", severity="BLOCKER", category="EXECUTION", message="blocked")],
    )
    results = {
        "get_strategy_contract": r("get_strategy_contract"),
        "validate_dataset": r("validate_dataset"),
        "run_temporal_semantics_tests": r("run_temporal_semantics_tests", {"causality_violations": 0}),
        "run_structural_backtest": r("run_structural_backtest", {"trades": 10}),
        "run_wfa": r("run_wfa", {"holdout": {"trades": 3, "net_expectancy_bps": 1.2, "profit_factor": 1.3}, "positive_oos_partition_fraction": 1.0}),
        "run_adversarial_review": r("run_adversarial_review", {"report": report.model_dump(mode="json")}),
    }
    decision = DeterministicCertificationJudge(gates()).decide(results)
    assert decision.verdict == "REJECTED_EXECUTION_FRAGILE"
    assert not decision.passed
