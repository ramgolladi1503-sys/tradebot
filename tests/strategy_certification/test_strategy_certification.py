import pytest
import dataclasses
import time
from unittest.mock import MagicMock
from datetime import date

from core.strategy_registry.strategy_manifest import StrategyManifest
from core.strategy_registry.strategy_contract import StrategyContract

from core.strategy_truth.truth_models import StrategyTruthReport, StrategySourceEvidence
from core.strategy_truth.truth_types import ImplementationVerdict
from core.strategy_truth.semantic_comparator import SemanticResult, SemanticClassification
from core.strategy_truth.mathematical_auditor import MathematicalResult, MathematicalClassification

from core.outcome_evidence.evidence_models import OutcomeEvidenceRunSummary

from core.statistical_validation.statistics_models import (
    StatisticalValidationReport, SampleValidationReport, ExpectancyReport, 
    ProfitFactorReport, DrawdownReport, DistributionReport, BootstrapReport,
    CostSensitivityReport, RegimeReport, WalkForwardReport, StabilityReport
)
from core.statistical_validation.statistics_types import ValidationStatus, SignificanceLevel, StabilityStatus, DrawdownStatus

from core.strategy_certification.certification_types import CertificationState, GateStatus
from core.strategy_certification.certification_engine import CertificationEngine
from core.strategy_certification.eligibility import RegistryGate
from core.strategy_certification.truth_gate import TruthGate
from core.strategy_certification.evidence_gate import EvidenceGate
from core.strategy_certification.statistics_gate import StatisticsGate
from core.strategy_certification.risk_gate import RiskGate
from core.strategy_certification.report_generator import ReportGenerator
from core.strategy_certification.audit_log import AuditLogger
from core.strategy_certification.validation import CertificationPolicyValidator

# Helpers to build mock objects
def build_contract(missing_field: str = "") -> StrategyContract:
    contract = StrategyContract(
        strategy_id="TEST_STRAT", strategy_name="Test Strat", version="1.0",
        owner="owner", created_date=date.today(), description="desc",
        market_hypothesis="H", primary_market="NSE", supported_indices=[],
        supported_option_types=[],
        entry_rules_summary="E", exit_rules_summary="X",
        stop_logic_summary="S", target_logic_summary="T",
        time_stop="15:15", required_indicators=["PRICE"], required_market_data=["PRICE"],
        required_option_data=[], required_sessions=[], required_liquidity="HIGH",
        allowed_regimes=[], forbidden_regimes=[], required_confirmations=[],
        known_limitations=[], known_assumptions=[]
    )
    if missing_field:
        return dataclasses.replace(contract, **{missing_field: ""}) # type: ignore
    return contract

def build_manifest(missing_field: str = "") -> StrategyManifest:
    contract = build_contract(missing_field)
    return StrategyManifest(contract=contract, file_path="t", module_path="t")

def build_truth(verdict=ImplementationVerdict.IMPLEMENTATION_VERIFIED, sem=SemanticClassification.SEMANTIC_MATCH, math=MathematicalClassification.MATHEMATICAL_MATCH) -> StrategyTruthReport:
    return StrategyTruthReport(
        strategy_id="TEST_STRAT", is_registry_complete=True, verdict=verdict,
        source_evidence=StrategySourceEvidence("TEST_STRAT", [], [], [], [], [], [], [], [], [], [], []),
        rule_comparisons=[], parameter_findings=[], heuristic_findings=[], indicator_findings=[], dependency_findings=[],
        semantic_results=[SemanticResult(classification=sem, expected_concept="", graph_evidence="", missing_evidence="")],
        mathematical_result=MathematicalResult(classification=math, reason="")
    )

def build_evidence(insufficient=0, ambiguous=0, weak=0, exec_count=100) -> OutcomeEvidenceRunSummary:
    return OutcomeEvidenceRunSummary("r", "C", 100, exec_count, 0, insufficient, ambiguous, weak, 0.0, time.time())

def build_stats(
    sample_status=ValidationStatus.VALID,
    boot_status=SignificanceLevel.HIGH_CONFIDENCE,
    stab_status=StabilityStatus.STABLE,
    wf_status=StabilityStatus.STABLE,
    regime_status=ValidationStatus.VALID,
    dd_status=DrawdownStatus.WITHIN_LIMITS,
    warnings=None
) -> StatisticalValidationReport:
    return StatisticalValidationReport(
        run_id="r",
        sample_validation=SampleValidationReport(status=sample_status, total_records=100, usable_sample_size=100, rejected_sample_size=0, insufficient_evidence_count=0, ambiguous_count=0, missing_trace_count=0, executable_count=100, hypothetical_count=0),
        expectancy=ExpectancyReport(status=ValidationStatus.VALID),
        profit_factor=ProfitFactorReport(status=ValidationStatus.VALID),
        drawdown=DrawdownReport(status=dd_status),
        distribution=DistributionReport(status=ValidationStatus.VALID),
        bootstrap=BootstrapReport(status=boot_status),
        cost_sensitivity=CostSensitivityReport(status=ValidationStatus.VALID),
        regime_analysis=RegimeReport(status=regime_status),
        walk_forward=WalkForwardReport(status=wf_status),
        stability=StabilityReport(status=stab_status),
        warnings=warnings or [], limitations=[], assumptions=[]
    )

# 1-5. RegistryGate Tests
def test_registry_gate_pass():
    res = RegistryGate.evaluate(build_manifest())
    assert res.status == GateStatus.PASS

def test_registry_gate_missing_manifest():
    res = RegistryGate.evaluate(None)
    assert res.status == GateStatus.FAIL
    assert "Missing StrategyManifest" in res.blockers[0]

def test_registry_gate_missing_id():
    mock_manifest = MagicMock()
    mock_manifest.contract = MagicMock()
    mock_manifest.contract.strategy_id = ""
    mock_manifest.contract.version = "1.0"
    mock_manifest.contract.market_hypothesis = "H"
    res = RegistryGate.evaluate(mock_manifest)
    assert res.status == GateStatus.FAIL
    assert "strategy_id" in res.blockers[0]

def test_registry_gate_missing_version():
    mock_manifest = MagicMock()
    mock_manifest.contract = MagicMock()
    mock_manifest.contract.strategy_id = "TEST_STRAT"
    mock_manifest.contract.version = ""
    mock_manifest.contract.market_hypothesis = "H"
    res = RegistryGate.evaluate(mock_manifest)
    assert res.status == GateStatus.FAIL
    assert "version" in res.blockers[0]

def test_registry_gate_missing_hypothesis():
    mock_manifest = MagicMock()
    mock_manifest.contract = MagicMock()
    mock_manifest.contract.strategy_id = "TEST_STRAT"
    mock_manifest.contract.version = "1.0"
    mock_manifest.contract.market_hypothesis = ""
    res = RegistryGate.evaluate(mock_manifest)
    assert res.status == GateStatus.FAIL
    assert "market_hypothesis" in res.blockers[0]

# 6-10. TruthGate Tests
def test_truth_gate_pass():
    res = TruthGate.evaluate(build_truth())
    assert res.status == GateStatus.PASS

def test_truth_gate_missing_report():
    res = TruthGate.evaluate(None)
    assert res.status == GateStatus.FAIL

def test_truth_gate_implementation_mismatch():
    res = TruthGate.evaluate(build_truth(verdict=ImplementationVerdict.IMPLEMENTATION_MISMATCH))
    assert res.status == GateStatus.FAIL
    assert "mismatch" in res.blockers[0].lower()

def test_truth_gate_semantic_mismatch():
    res = TruthGate.evaluate(build_truth(sem=SemanticClassification.SEMANTIC_MISMATCH))
    assert res.status == GateStatus.FAIL
    assert "Semantic Mismatch" in res.blockers[0]

def test_truth_gate_mathematical_mismatch():
    res = TruthGate.evaluate(build_truth(math=MathematicalClassification.MATHEMATICAL_MISMATCH))
    assert res.status == GateStatus.FAIL
    assert "Mathematical Mismatch" in res.blockers[0]

# 11-15. EvidenceGate Tests
def test_evidence_gate_pass():
    res = EvidenceGate.evaluate(build_evidence())
    assert res.status == GateStatus.PASS

def test_evidence_gate_missing():
    res = EvidenceGate.evaluate(None)
    assert res.status == GateStatus.FAIL

def test_evidence_gate_insufficient():
    res = EvidenceGate.evaluate(build_evidence(insufficient=5))
    assert res.status == GateStatus.FAIL
    assert "insufficient" in res.blockers[0]

def test_evidence_gate_ambiguous():
    res = EvidenceGate.evaluate(build_evidence(ambiguous=2))
    assert res.status == GateStatus.FAIL

def test_evidence_gate_unusable():
    res = EvidenceGate.evaluate(build_evidence(weak=1))
    assert res.status == GateStatus.FAIL

# 16-21. StatisticsGate Tests
def test_stats_gate_pass():
    res = StatisticsGate.evaluate(build_stats())
    assert res.status == GateStatus.PASS

def test_stats_gate_missing():
    res = StatisticsGate.evaluate(None)
    assert res.status == GateStatus.FAIL

def test_stats_gate_insufficient_sample():
    res = StatisticsGate.evaluate(build_stats(sample_status=ValidationStatus.INSUFFICIENT_SAMPLE))
    assert res.status == GateStatus.FAIL

def test_stats_gate_low_confidence():
    res = StatisticsGate.evaluate(build_stats(boot_status=SignificanceLevel.LOW_CONFIDENCE))
    assert res.status == GateStatus.FAIL

def test_stats_gate_unstable():
    res = StatisticsGate.evaluate(build_stats(stab_status=StabilityStatus.UNSTABLE))
    assert res.status == GateStatus.FAIL

def test_stats_gate_wf_unstable():
    res = StatisticsGate.evaluate(build_stats(wf_status=StabilityStatus.UNSTABLE))
    assert res.status == GateStatus.FAIL

# 22-24. RiskGate Tests
def test_risk_gate_pass():
    res = RiskGate.evaluate(build_stats(), build_evidence())
    assert res.status == GateStatus.PASS
    assert not res.warnings

def test_risk_gate_excessive_drawdown():
    res = RiskGate.evaluate(build_stats(dd_status=DrawdownStatus.EXCESSIVE), build_evidence())
    assert res.status == GateStatus.WARNING
    assert "EXCESSIVE" in res.warnings[0]

def test_risk_gate_stale_evidence():
    ev = build_evidence()
    ev = dataclasses.replace(ev, end_time=time.time() - (40 * 24 * 3600))
    res = RiskGate.evaluate(build_stats(), ev)
    assert res.status == GateStatus.WARNING
    assert "30 days" in res.warnings[0]

# 25-29. CertificationEngine Tests
def test_engine_happy_path():
    report = CertificationEngine.run_certification(build_manifest(), build_truth(), build_evidence(), build_stats())
    assert report.final_state == CertificationState.PRODUCTION_CANDIDATE

def test_engine_rejected_initial_state():
    report = CertificationEngine.run_certification(build_manifest(), build_truth(), build_evidence(), build_stats(), initial_state=CertificationState.REJECTED)
    assert report.final_state == CertificationState.REJECTED

def test_engine_suspended_initial_state():
    report = CertificationEngine.run_certification(build_manifest(), build_truth(), build_evidence(), build_stats(), initial_state=CertificationState.SUSPENDED)
    assert report.final_state == CertificationState.SUSPENDED

def test_engine_revoked_initial_state():
    report = CertificationEngine.run_certification(build_manifest(), build_truth(), build_evidence(), build_stats(), initial_state=CertificationState.REVOKED)
    assert report.final_state == CertificationState.REVOKED

def test_engine_truth_failure_is_research_only():
    report = CertificationEngine.run_certification(build_manifest(), build_truth(verdict=ImplementationVerdict.IMPLEMENTATION_MISMATCH), build_evidence(), build_stats())
    assert report.final_state == CertificationState.RESEARCH_ONLY

def test_engine_evidence_failure_is_insufficient():
    report = CertificationEngine.run_certification(build_manifest(), build_truth(), build_evidence(insufficient=10), build_stats())
    assert report.final_state == CertificationState.INSUFFICIENT_EVIDENCE

def test_engine_stats_failure_is_insufficient():
    report = CertificationEngine.run_certification(build_manifest(), build_truth(), build_evidence(), build_stats(sample_status=ValidationStatus.INSUFFICIENT_SAMPLE))
    assert report.final_state == CertificationState.INSUFFICIENT_EVIDENCE

# 30-32. Validation & Reporting
def test_validator_pass():
    report = CertificationEngine.run_certification(build_manifest(), build_truth(), build_evidence(), build_stats())
    assert CertificationPolicyValidator.validate_report(report) is True

def test_validator_fails_upgrades():
    report = CertificationEngine.run_certification(build_manifest(), build_truth(), build_evidence(), build_stats(), initial_state=CertificationState.REJECTED)
    object.__setattr__(report, "final_state", CertificationState.PRODUCTION_CANDIDATE)
    with pytest.raises(ValueError):
        CertificationPolicyValidator.validate_report(report)

def test_report_generator_writes_files(tmp_path):
    report = CertificationEngine.run_certification(build_manifest(), build_truth(), build_evidence(), build_stats())
    gen = ReportGenerator(str(tmp_path))
    gen.generate_all(report)
    
    assert (tmp_path / "01_registry_gate.md").exists()
    assert (tmp_path / "10_certification_summary.md").exists()
    
    content = (tmp_path / "10_certification_summary.md").read_text()
    assert "PRODUCTION_CANDIDATE" in content
    assert "does not guarantee profitability" in content

def test_audit_log_writes_file(tmp_path):
    report = CertificationEngine.run_certification(build_manifest(), build_truth(), build_evidence(), build_stats())
    log_path = tmp_path / "audit.md"
    logger = AuditLogger(str(log_path))
    logger.log(report)
    
    assert log_path.exists()
    content = log_path.read_text()
    assert "TEST_STRAT" in content
    assert "PRODUCTION_CANDIDATE" in content
