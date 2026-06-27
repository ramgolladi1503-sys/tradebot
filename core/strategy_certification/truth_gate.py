from typing import Optional
from core.strategy_truth.truth_models import StrategyTruthReport
from core.strategy_truth.truth_types import ImplementationVerdict
from core.strategy_truth.semantic_comparator import SemanticClassification
from core.strategy_truth.mathematical_auditor import MathematicalClassification
from core.strategy_certification.certification_models import GateResult
from core.strategy_certification.certification_types import GateStatus

class TruthGate:
    """
    Gate 2 - Truth
    
    Consume Strategy Truth Report.
    If:
    - implementation mismatch
    - manual review
    - semantic mismatch
    - mathematical mismatch
    
    Never allow: PAPER_ONLY
    Remain: RESEARCH_ONLY
    """

    @staticmethod
    def evaluate(report: Optional[StrategyTruthReport]) -> GateResult:
        if report is None:
            return GateResult(
                status=GateStatus.FAIL,
                reason="Strategy Truth Report is missing.",
                blockers=["Missing Truth Report"]
            )
            
        blockers = []
        
        # Implementation mismatch or manual review
        if report.verdict in (ImplementationVerdict.IMPLEMENTATION_MISMATCH, ImplementationVerdict.REQUIRES_MANUAL_REVIEW, ImplementationVerdict.HARDENED_ENGINE_MISMATCH):
            blockers.append(f"Implementation Verdict implies mismatch or manual review: {report.verdict.name}")
            
        # Semantic mismatch
        for sem_res in report.semantic_results:
            if sem_res.classification in (SemanticClassification.SEMANTIC_MISMATCH, SemanticClassification.SEMANTIC_CONTRADICTION):
                blockers.append(f"Semantic Mismatch: {sem_res.classification.name}")
                
        # Mathematical mismatch
        if report.mathematical_result:
            if report.mathematical_result.classification == MathematicalClassification.MATHEMATICAL_MISMATCH:
                blockers.append("Mathematical Mismatch")
                
        if blockers:
            return GateResult(
                status=GateStatus.FAIL,
                reason="Strategy Truth mismatches found. Must remain RESEARCH_ONLY.",
                blockers=blockers
            )
            
        return GateResult(
            status=GateStatus.PASS,
            reason="Strategy Truth Report passes all requirements."
        )
