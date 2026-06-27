import uuid
from typing import List, Optional
from core.outcome_evidence.evidence_models import OutcomeEvidenceRecord
from core.outcome_evidence.evidence_types import EvidenceQuality, OutcomeStatus
from .statistics_models import StatisticalValidationReport
from .statistics_types import ValidationStatus
from .statistics_config import ValidationConfig
from .sample_validator import validate_sample
from .expectancy import compute_expectancy
from .profit_factor import compute_profit_factor
from .drawdown import compute_drawdown
from .distribution import compute_distributions
from .bootstrap import compute_bootstrap
from .cost_sensitivity import compute_cost_sensitivity
from .regime_analysis import compute_regime_analysis
from .walk_forward import compute_walk_forward
from .stability import compute_stability

class ValidationEngine:
    def __init__(self, run_id: Optional[str] = None, config: Optional[ValidationConfig] = None):
        self.run_id = run_id or str(uuid.uuid4())
        self.config = config or ValidationConfig()
        
    def validate(self, records: List[OutcomeEvidenceRecord]) -> StatisticalValidationReport:
        """
        Runs the full statistical validation pipeline on the given records.
        """
        # Phase 2: Sample Validation
        sample_report = validate_sample(records, self.config)
        
        # Filter for usable records (only those that are strictly valid for statistical analysis)
        usable_records = []
        for r in records:
            if not r.simulation.is_hypothetical_rejected and \
               r.evidence_quality in (EvidenceQuality.COMPLETE, EvidenceQuality.PARTIAL) and \
               r.outcome_status not in (OutcomeStatus.AMBIGUOUS_BOTH_HIT, OutcomeStatus.NO_TRACE_DATA, OutcomeStatus.INSUFFICIENT_CANDIDATE_FIELDS, OutcomeStatus.PENDING):
                usable_records.append(r)
                
        # If the sample is insufficient, we still run the downstream tasks but they will
        # return INSUFFICIENT_SAMPLE objects instead of extrapolating.
        expectancy = compute_expectancy(usable_records)
        pf = compute_profit_factor(usable_records)
        drawdown = compute_drawdown(usable_records)
        distributions = compute_distributions(usable_records)
        bootstrap = compute_bootstrap(usable_records, self.config)
        cost_sens = compute_cost_sensitivity(usable_records, self.config)
        regimes = compute_regime_analysis(usable_records, self.config)
        walk_forward = compute_walk_forward(usable_records, self.config)
        stability = compute_stability(usable_records, self.config)
        
        warnings = []
        limitations = [
            "This report is purely statistical and does NOT claim strategy edge.",
            "Past performance is not indicative of future results.",
            "Hypothetical and rejected trades are excluded from the main statistical sample."
        ]
        
        if sample_report.status == ValidationStatus.INSUFFICIENT_SAMPLE:
            warnings.append("Insufficient sample size to compute reliable metrics.")
            
        return StatisticalValidationReport(
            run_id=self.run_id,
            sample_validation=sample_report,
            expectancy=expectancy,
            profit_factor=pf,
            drawdown=drawdown,
            distribution=distributions,
            bootstrap=bootstrap,
            cost_sensitivity=cost_sens,
            regime_analysis=regimes,
            walk_forward=walk_forward,
            stability=stability,
            warnings=warnings,
            limitations=limitations,
            assumptions=["Metrics assume standard slippage and spread where traces are missing."]
        )
