from typing import Optional
from core.outcome_evidence.evidence_models import OutcomeEvidenceRunSummary
from core.strategy_certification.certification_models import GateResult
from core.strategy_certification.certification_types import GateStatus

class EvidenceGate:
    """
    Gate 3 - Evidence
    
    Consume Outcome Evidence Summary.
    Reject certification if:
    - insufficient evidence
    - ambiguous dominance
    - missing traces
    - unusable evidence
    
    Fails back to: INSUFFICIENT_EVIDENCE
    """

    @staticmethod
    def evaluate(summary: Optional[OutcomeEvidenceRunSummary]) -> GateResult:
        if summary is None:
            return GateResult(
                status=GateStatus.FAIL,
                reason="Outcome Evidence Summary is missing.",
                blockers=["Missing Evidence Summary"]
            )
            
        blockers = []
        
        if summary.insufficient_evidence_count > 0:
            blockers.append(f"{summary.insufficient_evidence_count} records had insufficient evidence or missing traces.")
            
        if summary.ambiguous_count > 0:
            blockers.append(f"{summary.ambiguous_count} records had ambiguous dominance.")
            
        if summary.weak_ltp_count > 0:
            blockers.append(f"{summary.weak_ltp_count} records had weak LTP (unusable evidence).")
            
        if summary.executable_count == 0:
            blockers.append("No executable evidence records found.")
            
        if blockers:
            return GateResult(
                status=GateStatus.FAIL,
                reason="Outcome Evidence is insufficient, ambiguous, or unusable.",
                blockers=blockers
            )
            
        return GateResult(
            status=GateStatus.PASS,
            reason="Outcome Evidence is clean and usable."
        )
