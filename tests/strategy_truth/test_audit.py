import pytest
import os
import tempfile
from core.strategy_truth.truth_models import (
    ParameterFinding, 
    StrategyTruthReport, StrategyTruthSummary
)
from core.strategy_truth.truth_types import (
    RuleComparisonStatus, ParameterClassification, HeuristicClassification, 
    IndicatorStatus, ImplementationVerdict
)
from core.strategy_truth.registry_bridge import load_registry_bridge
from core.strategy_truth.source_scanner import SourceScanner
from core.strategy_truth.rule_extractor import RuleExtractor
from core.strategy_truth.parameter_auditor import ParameterAuditor
from core.strategy_truth.heuristic_detector import HeuristicDetector
from core.strategy_truth.dependency_analyzer import DependencyAnalyzer
from core.strategy_truth.implementation_auditor import ImplementationAuditor
from core.strategy_truth.report_generator import ReportGenerator
from tests.strategy_truth.fixtures.dummy_strat import contract


def test_registry_bridge():
    bridge = load_registry_bridge("tests/strategy_truth/fixtures")
    assert isinstance(bridge.manifests, dict)
    assert isinstance(bridge.incomplete_strategies, list)

def test_source_scanner():
    scanner = SourceScanner("dummy_strat", "tests/strategy_truth/fixtures/dummy_strat.py")
    evidence = scanner.scan()
    assert "DummyStrat" in evidence.classes
    assert "execute_order" in evidence.functions
    assert "THRESHOLD" in evidence.constants
    assert "RSI" in evidence.indicator_names
    assert "42" in evidence.parameter_literals
    assert "execute_order" in evidence.execution_hooks

def test_rule_extractor():
    extractor = RuleExtractor("dummy_strat", "tests/strategy_truth/fixtures/dummy_strat.py")
    evidence = extractor.extract()
    # Check if docstring extracted
    assert any("Entry rules: MACD crosses signal." in e.evidence_text for e in evidence)
    # Check line numbers exist
    assert all(e.line_number is not None for e in evidence)

def test_parameter_auditor():
    auditor = ParameterAuditor("tests/strategy_truth/fixtures/dummy_strat.py")
    findings = auditor.audit()
    assert any(f.name == "THRESHOLD" and f.classification == ParameterClassification.MAGIC_NUMBER for f in findings)
    assert any(f.name == "RSI" and f.classification == ParameterClassification.MAGIC_NUMBER for f in findings)
    # Ensure it doesn't modify files (by definition it just reads)

def test_heuristic_detector():
    detector = HeuristicDetector("tests/strategy_truth/fixtures/dummy_strat.py")
    findings = detector.audit()
    classifications = [f.classification for f in findings]
    assert HeuristicClassification.SAFE_COMMENT in classifications  # TODO
    assert HeuristicClassification.HEURISTIC_RISK in classifications  # score +=
    assert HeuristicClassification.PROBABILITY_LABEL_RISK in classifications  # probability

def test_dependency_analyzer():
    scanner = SourceScanner("dummy_strat", "tests/strategy_truth/fixtures/dummy_strat.py")
    evidence = scanner.scan()
    analyzer = DependencyAnalyzer(contract, evidence)
    findings = analyzer.analyze()
    # execute_order should be caught as execution hook direct coupling
    assert any(f.dependency_type == "execution hook" and f.is_direct_coupling for f in findings)
    # NIFTY_SPOT should be missing
    assert any(f.dependency_name == "NIFTY_SPOT" and f.is_unused for f in findings)

def test_implementation_auditor():
    scanner = SourceScanner("dummy_strat", "tests/strategy_truth/fixtures/dummy_strat.py")
    evidence = scanner.scan()
    extractor = RuleExtractor("dummy_strat", "tests/strategy_truth/fixtures/dummy_strat.py")
    rule_evidence = extractor.extract()
    auditor = ImplementationAuditor(contract, evidence, rule_evidence)
    
    comparisons = auditor.audit_rules()
    # Entry rules should match
    entry_comp = next(c for c in comparisons if c.registry_field == "entry_rules_summary")
    assert entry_comp.status in (RuleComparisonStatus.MATCH, RuleComparisonStatus.PARTIAL_MATCH)

    inds = auditor.audit_indicators()
    # RSI declared and used
    assert any(i.indicator_name == "RSI" and i.status == IndicatorStatus.DECLARED_AND_USED for i in inds)
    # MACD declared but not found
    assert any(i.indicator_name == "MACD" and i.status == IndicatorStatus.DECLARED_BUT_NOT_FOUND for i in inds)

def test_immutable_models():
    finding = ParameterFinding("test", "1", ParameterClassification.UNKNOWN, "test.py")
    with pytest.raises(Exception):
        finding.name = "changed"

def test_report_generator():
    with tempfile.TemporaryDirectory() as tmpdir:
        generator = ReportGenerator(output_dir=tmpdir)
        summary = StrategyTruthSummary(
            total_strategies=1,
            registry_incomplete_count=0,
            fully_verified_count=0,
            partially_verified_count=1,
            mismatch_count=0,
            reports=[
                StrategyTruthReport(
                    strategy_id="dummy",
                    is_registry_complete=True,
                    verdict=ImplementationVerdict.PARTIALLY_VERIFIED,
                    source_evidence=None, # type: ignore
                    rule_comparisons=[],
                    parameter_findings=[],
                    heuristic_findings=[],
                    indicator_findings=[],
                    dependency_findings=[],
                )
            ]
        )
        generator.write_reports(summary)
        
        assert os.path.exists(os.path.join(tmpdir, "01_loaded_registry.md"))
        assert os.path.exists(os.path.join(tmpdir, "06_strategy_truth_summary.md"))
