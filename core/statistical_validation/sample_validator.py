from typing import List, Optional
from core.outcome_evidence.evidence_models import OutcomeEvidenceRecord
from core.outcome_evidence.evidence_types import EvidenceQuality, OutcomeStatus
from .statistics_models import SampleValidationReport
from .statistics_types import ValidationStatus
from .statistics_config import ValidationConfig

def validate_sample(records: List[OutcomeEvidenceRecord], config: Optional[ValidationConfig] = None) -> SampleValidationReport:
    """
    Validates the provided sample of evidence records.
    Filters out rejected, missing, ambiguous, or insufficient records from the usable count.
    """
    if config is None:
        config = ValidationConfig()
        
    total = len(records)
    
    insufficient = 0
    ambiguous = 0
    missing_trace = 0
    hypothetical = 0
    rejected = 0
    executable = 0
    usable = 0
    
    for r in records:
        if r.evidence_quality in (EvidenceQuality.INSUFFICIENT, EvidenceQuality.UNUSABLE):
            insufficient += 1
            
        if r.outcome_status == OutcomeStatus.AMBIGUOUS_BOTH_HIT:
            ambiguous += 1
            
        if r.outcome_status == OutcomeStatus.NO_TRACE_DATA:
            missing_trace += 1
            
        if r.simulation.is_hypothetical_rejected:
            hypothetical += 1
            
        # The true execution eligibility isn't stored as a direct enum on OutcomeEvidenceRecord,
        # but we can infer it. Hypothetically rejected candidates are typically ExecutionEligibility.REJECTED.
        # Alternatively, if there are blockers, it was rejected. We map `is_hypothetical_rejected` to rejected.
        if r.simulation.is_hypothetical_rejected:
            rejected += 1
        else:
            executable += 1
            
        # A usable record for statistical significance is one that was executable, complete/partial, 
        # and has a valid outcome status (TARGET_HIT, STOP_HIT, TIME_STOP, OPEN_AT_END).
        if not r.simulation.is_hypothetical_rejected and \
           r.evidence_quality in (EvidenceQuality.COMPLETE, EvidenceQuality.PARTIAL) and \
           r.outcome_status not in (OutcomeStatus.AMBIGUOUS_BOTH_HIT, OutcomeStatus.NO_TRACE_DATA, OutcomeStatus.INSUFFICIENT_CANDIDATE_FIELDS, OutcomeStatus.PENDING):
            usable += 1

    status = ValidationStatus.VALID if usable >= config.minimum_usable_sample_size else ValidationStatus.INSUFFICIENT_SAMPLE
    
    return SampleValidationReport(
        total_records=total,
        usable_sample_size=usable,
        rejected_sample_size=rejected,
        insufficient_evidence_count=insufficient,
        ambiguous_count=ambiguous,
        missing_trace_count=missing_trace,
        executable_count=executable,
        hypothetical_count=hypothetical,
        status=status
    )
