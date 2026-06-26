from typing import List
from core.strategy_truth.truth_models import (
    RuleComparison, RuleEvidence, IndicatorFinding, StrategySourceEvidence
)
from core.strategy_truth.truth_types import RuleComparisonStatus, IndicatorStatus, ImplementationVerdict
from core.strategy_registry.strategy_contract import StrategyContract


class ImplementationAuditor:
    """Compares registry contract vs implementation evidence."""

    def __init__(
        self, 
        contract: StrategyContract, 
        source_evidence: StrategySourceEvidence,
        rule_evidence: List[RuleEvidence]
    ):
        self.contract = contract
        self.source_evidence = source_evidence
        self.rule_evidence = rule_evidence

    def _compare_rule(self, field_name: str, expected: str, expected_type: str) -> RuleComparison:
        if not expected or expected.lower() == "none":
            return RuleComparison(
                registry_field=field_name,
                expected_description=expected,
                status=RuleComparisonStatus.MISSING_IN_IMPLEMENTATION,
                reason="No expected logic defined, but checking if extra exists.",
            )

        # Naive matching based on evidence type
        matching_evidence = [e for e in self.rule_evidence if expected_type in e.evidence_type]
        
        if not matching_evidence:
            return RuleComparison(
                registry_field=field_name,
                expected_description=expected,
                status=RuleComparisonStatus.MISSING_IN_IMPLEMENTATION,
                reason=f"No code evidence found for {expected_type}.",
            )
        
        evidence = matching_evidence[0]
        # Very naive text matching
        if any(word in evidence.evidence_text.lower() for word in expected.lower().split()):
            return RuleComparison(
                registry_field=field_name,
                expected_description=expected,
                status=RuleComparisonStatus.MATCH,
                reason=f"Evidence strongly supports {expected_type}.",
                implementation_evidence=evidence.evidence_text,
                file_path=evidence.file_path,
                line_number=evidence.line_number,
            )
        else:
            return RuleComparison(
                registry_field=field_name,
                expected_description=expected,
                status=RuleComparisonStatus.PARTIAL_MATCH,
                reason="Evidence found but exact words may not match.",
                implementation_evidence=evidence.evidence_text,
                file_path=evidence.file_path,
                line_number=evidence.line_number,
            )

    def audit_rules(self) -> List[RuleComparison]:
        comparisons = []
        
        comparisons.append(self._compare_rule("entry_rules_summary", self.contract.entry_rules_summary, "entry"))
        comparisons.append(self._compare_rule("exit_rules_summary", self.contract.exit_rules_summary, "exit"))
        comparisons.append(self._compare_rule("stop_logic_summary", self.contract.stop_logic_summary, "stop"))
        comparisons.append(self._compare_rule("target_logic_summary", self.contract.target_logic_summary, "target"))
        comparisons.append(self._compare_rule("time_stop", self.contract.time_stop, "time-stop"))

        return comparisons

    def audit_indicators(self) -> List[IndicatorFinding]:
        findings = []
        declared = [i.upper() for i in self.contract.required_indicators]
        used = [i.upper() for i in self.source_evidence.indicator_names]

        for ind in declared:
            if ind in used:
                findings.append(IndicatorFinding(ind, IndicatorStatus.DECLARED_AND_USED, "Found in registry and code."))
            else:
                findings.append(IndicatorFinding(ind, IndicatorStatus.DECLARED_BUT_NOT_FOUND, "In registry but not in code."))

        for ind in used:
            if ind not in declared:
                findings.append(IndicatorFinding(ind, IndicatorStatus.USED_BUT_NOT_DECLARED, "In code but not in registry."))

        return findings

    def determine_verdict(self, comparisons: List[RuleComparison]) -> ImplementationVerdict:
        has_missing = any(c.status == RuleComparisonStatus.MISSING_IN_IMPLEMENTATION for c in comparisons)
        has_partial = any(c.status == RuleComparisonStatus.PARTIAL_MATCH for c in comparisons)
        
        if has_missing:
            return ImplementationVerdict.IMPLEMENTATION_MISMATCH
        if has_partial:
            return ImplementationVerdict.PARTIALLY_VERIFIED
        
        return ImplementationVerdict.IMPLEMENTATION_VERIFIED
