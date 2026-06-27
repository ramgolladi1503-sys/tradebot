from typing import Optional
from core.statistical_validation.statistics_models import StatisticalValidationReport
from core.outcome_evidence.evidence_models import OutcomeEvidenceRunSummary
from core.statistical_validation.statistics_types import DrawdownStatus, StabilityStatus
from core.strategy_certification.certification_models import GateResult
from core.strategy_certification.certification_types import GateStatus

class RiskGate:
    """
    Gate 5 - Risk
    
    This gate is governance only.
    Verify:
    - drawdown acceptable
    - instability warnings
    - evidence freshness
    - replay age
    - regime coverage
    
    Return warnings.
    Do not change certification automatically.
    """

    @staticmethod
    def evaluate(
        stats_report: Optional[StatisticalValidationReport],
        evidence_summary: Optional[OutcomeEvidenceRunSummary]
    ) -> GateResult:
        warnings: list[str] = []
        limitations: list[str] = []
        
        if stats_report is None or evidence_summary is None:
            return GateResult(
                status=GateStatus.WARNING,
                reason="Cannot fully evaluate risk due to missing inputs.",
                warnings=["Missing statistics or evidence for risk check."],
                limitations=["Risk evaluation skipped."]
            )

        # Drawdown acceptable
        if hasattr(stats_report.drawdown, 'status') and stats_report.drawdown.status == DrawdownStatus.EXCESSIVE:
            warnings.append("Drawdown profile is EXCESSIVE.")
            
        # Instability warnings
        if stats_report.warnings:
            warnings.extend(stats_report.warnings)
            
        # Regime coverage
        if hasattr(stats_report.regime_analysis, 'status') and stats_report.regime_analysis.status == StabilityStatus.INSUFFICIENT_DATA:
            limitations.append("Regime coverage has insufficient data.")
            
        # Evidence freshness and replay age (using end_time of evidence)
        import time
        current_time = time.time()
        age_seconds = current_time - evidence_summary.end_time
        # Warning if older than 30 days
        if age_seconds > (30 * 24 * 3600):
            warnings.append("Evidence replay is older than 30 days. Freshness warning.")
            
        if warnings or limitations:
            return GateResult(
                status=GateStatus.WARNING,
                reason="Governance risk warnings identified.",
                limitations=limitations,
                warnings=warnings
            )
            
        return GateResult(
            status=GateStatus.PASS,
            reason="No governance risk warnings found."
        )
