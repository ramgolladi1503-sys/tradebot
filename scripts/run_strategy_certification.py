import argparse
import sys
import logging
from datetime import date

from core.strategy_registry.strategy_manifest import StrategyManifest
from core.strategy_registry.strategy_contract import StrategyContract
from core.strategy_truth.truth_models import StrategyTruthReport, StrategySourceEvidence
from core.strategy_truth.truth_types import ImplementationVerdict
from core.outcome_evidence.evidence_models import OutcomeEvidenceRunSummary
from core.statistical_validation.statistics_models import (
    StatisticalValidationReport, SampleValidationReport, ExpectancyReport, 
    ProfitFactorReport, DrawdownReport, DistributionReport, BootstrapReport,
    CostSensitivityReport, RegimeReport, WalkForwardReport, StabilityReport
)
from core.statistical_validation.statistics_types import ValidationStatus, SignificanceLevel, StabilityStatus, DrawdownStatus

from core.strategy_certification.certification_types import CertificationState
from core.strategy_certification.certification_engine import CertificationEngine
from core.strategy_certification.report_generator import ReportGenerator
from core.strategy_certification.audit_log import AuditLogger
from core.strategy_certification.validation import CertificationPolicyValidator

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def create_mock_data():
    contract = StrategyContract(
        strategy_id="TEST_STRAT",
        strategy_name="Test Strategy",
        version="1.0",
        owner="test",
        created_date=date.today(),
        description="A test strategy",
        market_hypothesis="Test hypothesis",
        primary_market="NSE",
        supported_indices=[],
        supported_option_types=[],
        entry_rules_summary="entry",
        exit_rules_summary="exit",
        stop_logic_summary="stop",
        target_logic_summary="target",
        time_stop="15:15",
        required_indicators=["PRICE"],
        required_market_data=["PRICE"],
        required_option_data=[],
        required_sessions=[],
        required_liquidity="HIGH",
        allowed_regimes=[],
        forbidden_regimes=[],
        required_confirmations=[],
        known_limitations=[],
        known_assumptions=[]
    )
    manifest = StrategyManifest(contract=contract, file_path="test", module_path="test")

    truth_report = StrategyTruthReport(
        strategy_id="TEST_STRAT",
        is_registry_complete=True,
        verdict=ImplementationVerdict.IMPLEMENTATION_VERIFIED,
        source_evidence=StrategySourceEvidence("TEST_STRAT", [], [], [], [], [], [], [], [], [], [], []),
        rule_comparisons=[],
        parameter_findings=[],
        heuristic_findings=[],
        indicator_findings=[],
        dependency_findings=[]
    )

    evidence_summary = OutcomeEvidenceRunSummary(
        run_id="run1",
        run_status="COMPLETED",
        total_candidates=100,
        executable_count=100,
        rejected_count=0,
        insufficient_evidence_count=0,
        ambiguous_count=0,
        weak_ltp_count=0,
        start_time=0.0,
        end_time=0.0
    )

    stats_report = StatisticalValidationReport(
        run_id="run1",
        sample_validation=SampleValidationReport(status=ValidationStatus.VALID, total_records=100, usable_sample_size=100, rejected_sample_size=0, insufficient_evidence_count=0, ambiguous_count=0, missing_trace_count=0, executable_count=100, hypothetical_count=0),
        expectancy=ExpectancyReport(status=ValidationStatus.VALID),
        profit_factor=ProfitFactorReport(status=ValidationStatus.VALID),
        drawdown=DrawdownReport(status=DrawdownStatus.WITHIN_LIMITS),
        distribution=DistributionReport(status=ValidationStatus.VALID),
        bootstrap=BootstrapReport(status=SignificanceLevel.HIGH_CONFIDENCE),
        cost_sensitivity=CostSensitivityReport(status=ValidationStatus.VALID),
        regime_analysis=RegimeReport(status=ValidationStatus.VALID),
        walk_forward=WalkForwardReport(status=StabilityStatus.STABLE),
        stability=StabilityReport(status=StabilityStatus.STABLE),
        warnings=[],
        limitations=[],
        assumptions=[]
    )
    
    return manifest, truth_report, evidence_summary, stats_report

def main():
    parser = argparse.ArgumentParser(description="Run Strategy Certification Engine")
    parser.add_argument("--dry-run", action="store_true", help="Run with mock data")
    args = parser.parse_args()
    
    if args.dry_run:
        logging.info("Running with mock data")
        manifest, truth_report, evidence_summary, stats_report = create_mock_data()
    else:
        logging.error("Real execution requires loading reports from disk. Not implemented in this PR.")
        sys.exit(1)

    logging.info("Evaluating Certification Gates...")
    report = CertificationEngine.run_certification(
        manifest=manifest,
        truth_report=truth_report,
        evidence_summary=evidence_summary,
        statistics_report=stats_report,
        initial_state=CertificationState.RESEARCH_ONLY
    )
    
    logging.info(f"Final Certification State: {report.final_state.name}")
    
    logging.info("Validating policies...")
    CertificationPolicyValidator.validate_report(report)
    
    logging.info("Generating reports...")
    generator = ReportGenerator()
    generator.generate_all(report)
    
    logging.info("Writing audit log...")
    logger = AuditLogger()
    logger.log(report)
    
    logging.info("Done.")

if __name__ == "__main__":
    main()
