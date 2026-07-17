from agentic_research.contracts import ToolResult
from agentic_research.critics import DeterministicAdversarialCritic


def result(name, payload=None, blockers=None, status="SUCCESS"):
    return ToolResult(tool=name, status=status, payload=payload or {}, blockers=blockers or []).with_hash()


def test_critic_blocks_structural_mvp_from_execution_claim():
    report = DeterministicAdversarialCritic().review({
        "validate_dataset": result("validate_dataset", {"volume_dependent_claims_allowed": False}),
        "run_structural_backtest": result("run_structural_backtest", {"candidate_rows": [{"net_return_bps": 1.0}] * 12, "option_execution_certified": False}),
        "run_wfa": result("run_wfa", {"validation": {"net_expectancy_bps": 1.0}, "holdout": {"net_expectancy_bps": 1.0}, "purged_embargoed_option_wfa_used": False, "structural_mvp_only": True}),
    })
    codes = {finding.code for finding in report.blockers}
    assert "structural_split_not_purged_embargoed_wfa" in codes
    assert "option_execution_not_certified" in codes


def test_critic_maps_legacy_blockers():
    report = DeterministicAdversarialCritic().review({
        "audit_existing_research_report": result("audit_existing_research_report", {"volume_quality": "ZERO_VOLUME"}, blockers=["legacy_dataset_zero_volume"], status="REJECTED")
    })
    assert report.blockers[0].category == "DATA"
