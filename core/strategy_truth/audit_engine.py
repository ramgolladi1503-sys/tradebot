from typing import Optional
from core.strategy_truth.truth_models import StrategyTruthReport, StrategyTruthSummary
from core.strategy_truth.truth_types import ImplementationVerdict
from core.strategy_truth.registry_bridge import load_registry_bridge
from core.strategy_truth.source_scanner import SourceScanner
from core.strategy_truth.rule_extractor import RuleExtractor
from core.strategy_truth.parameter_auditor import ParameterAuditor
from core.strategy_truth.heuristic_detector import HeuristicDetector
from core.strategy_truth.dependency_analyzer import DependencyAnalyzer
from core.strategy_truth.implementation_auditor import ImplementationAuditor


class AuditEngine:
    """Orchestrates the Strategy Truth Engine."""

    def __init__(self, strategies_path: str = "strategies"):
        self.strategies_path = strategies_path
        self.bridge_result = load_registry_bridge(self.strategies_path)

    def run_all(self, target_strategy_id: Optional[str] = None) -> StrategyTruthSummary:
        reports = []
        fully_verified = 0
        partially_verified = 0
        mismatch = 0
        registry_incomplete = len(self.bridge_result.incomplete_strategies)

        for strat_id in self.bridge_result.incomplete_strategies:
            if target_strategy_id and target_strategy_id != strat_id:
                continue
            
            # Create a dummy report for incomplete
            reports.append(
                StrategyTruthReport(
                    strategy_id=strat_id,
                    is_registry_complete=False,
                    verdict=ImplementationVerdict.REGISTRY_INCOMPLETE,
                    source_evidence=None, # type: ignore
                    rule_comparisons=[],
                    parameter_findings=[],
                    heuristic_findings=[],
                    indicator_findings=[],
                    dependency_findings=[],
                )
            )

        for strat_id, manifest in self.bridge_result.manifests.items():
            if target_strategy_id and target_strategy_id != strat_id:
                continue

            file_path = manifest.file_path

            # Phase 2: Source Scanner
            scanner = SourceScanner(strat_id, file_path)
            source_evidence = scanner.scan()

            # Phase 3: Rule Extractor
            extractor = RuleExtractor(strat_id, file_path)
            rule_evidence = extractor.extract()

            # Phase 5: Parameter Auditor
            param_auditor = ParameterAuditor(file_path)
            parameter_findings = param_auditor.audit()

            # Phase 6: Heuristic Detector
            heur_detector = HeuristicDetector(file_path)
            heuristic_findings = heur_detector.audit()

            # Phase 8: Dependency Analyzer
            dep_analyzer = DependencyAnalyzer(manifest.contract, source_evidence)
            dependency_findings = dep_analyzer.analyze()

            # Phase 4 & 7: Implementation Auditor (Contract Comparison + Indicator Inventory)
            impl_auditor = ImplementationAuditor(manifest.contract, source_evidence, rule_evidence)
            rule_comparisons = impl_auditor.audit_rules()
            indicator_findings = impl_auditor.audit_indicators()

            verdict = impl_auditor.determine_verdict(rule_comparisons)
            
            if verdict == ImplementationVerdict.IMPLEMENTATION_VERIFIED:
                fully_verified += 1
            elif verdict == ImplementationVerdict.PARTIALLY_VERIFIED:
                partially_verified += 1
            else:
                mismatch += 1

            reports.append(
                StrategyTruthReport(
                    strategy_id=strat_id,
                    is_registry_complete=True,
                    verdict=verdict,
                    source_evidence=source_evidence,
                    rule_comparisons=rule_comparisons,
                    parameter_findings=parameter_findings,
                    heuristic_findings=heuristic_findings,
                    indicator_findings=indicator_findings,
                    dependency_findings=dependency_findings,
                    rule_evidence=rule_evidence,
                )
            )

        return StrategyTruthSummary(
            total_strategies=len(self.bridge_result.manifests) + registry_incomplete,
            registry_incomplete_count=registry_incomplete,
            fully_verified_count=fully_verified,
            partially_verified_count=partially_verified,
            mismatch_count=mismatch,
            reports=reports,
        )
