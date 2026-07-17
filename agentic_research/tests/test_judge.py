from agentic_research.certification import DeterministicCertificationJudge
from agentic_research.contracts import ToolResult


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


def test_dataset_failure_is_authoritative():
    results = {
        "get_strategy_contract": r("get_strategy_contract"),
        "validate_dataset": r("validate_dataset", status="REJECTED", blockers=["missing_field:context"]),
    }
    decision = DeterministicCertificationJudge(gates()).decide(results)
    assert decision.verdict == "REJECTED_DATA_INELIGIBLE"


def test_llm_cannot_promote_failed_wfa():
    results = {
        "get_strategy_contract": r("get_strategy_contract"),
        "validate_dataset": r("validate_dataset"),
        "run_temporal_semantics_tests": r("run_temporal_semantics_tests", {"causality_violations": 0}),
        "run_structural_backtest": r("run_structural_backtest", {"trades": 10}),
        "run_wfa": r("run_wfa", {"holdout": {"trades": 3, "net_expectancy_bps": -0.1, "profit_factor": 0.9}, "positive_oos_partition_fraction": 0.0}),
    }
    decision = DeterministicCertificationJudge(gates()).decide(results)
    assert decision.verdict == "REJECTED_OVERFIT"
    assert not decision.passed


def test_valid_structural_evidence_ceiling_is_option_replay():
    results = {
        "get_strategy_contract": r("get_strategy_contract"),
        "validate_dataset": r("validate_dataset"),
        "run_temporal_semantics_tests": r("run_temporal_semantics_tests", {"causality_violations": 0}),
        "run_structural_backtest": r("run_structural_backtest", {"trades": 10}),
        "run_wfa": r("run_wfa", {"holdout": {"trades": 3, "net_expectancy_bps": 1.2, "profit_factor": 1.3}, "positive_oos_partition_fraction": 1.0}),
    }
    decision = DeterministicCertificationJudge(gates()).decide(results)
    assert decision.verdict == "READY_FOR_OPTION_REPLAY"
    assert decision.passed
