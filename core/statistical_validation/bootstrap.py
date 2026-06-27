import random
from typing import List, Optional
from core.outcome_evidence.evidence_models import OutcomeEvidenceRecord
from .statistics_models import BootstrapReport, ConfidenceInterval
from .statistics_types import SignificanceLevel
from .statistics_config import ValidationConfig

# Seed for reproducibility in tests
def set_bootstrap_seed(seed: int) -> None:
    random.seed(seed)

def _compute_pf(records: List[OutcomeEvidenceRecord]) -> float:
    profits = sum(r.net_pnl for r in records if r.net_pnl > 0)
    losses = abs(sum(r.net_pnl for r in records if r.net_pnl < 0))
    if losses == 0:
        return 0.0 # Return 0 for undefined inside bootstrap to keep it simple, or better yet, return a high number
    return profits / losses

def _compute_expectancy(records: List[OutcomeEvidenceRecord]) -> float:
    return sum(r.net_pnl for r in records) / len(records) if records else 0.0

def _compute_mean_r(records: List[OutcomeEvidenceRecord]) -> float:
    rs = [r.mfe_mae.realized_r for r in records if r.mfe_mae is not None]
    return sum(rs) / len(rs) if rs else 0.0

def compute_bootstrap(usable_records: List[OutcomeEvidenceRecord], config: Optional[ValidationConfig] = None) -> BootstrapReport:
    """
    Computes confidence intervals using bootstrap resampling with replacement.
    """
    if config is None:
        config = ValidationConfig()
        
    random.seed(config.bootstrap_seed)
    
    n = len(usable_records)
    if n < config.minimum_usable_sample_size:
        return BootstrapReport(status=SignificanceLevel.INSUFFICIENT_SAMPLE)
        
    pf_estimates = []
    exp_estimates = []
    r_estimates = []
    
    for _ in range(config.bootstrap_iterations):
        sample = random.choices(usable_records, k=n)
        pf_estimates.append(_compute_pf(sample))
        exp_estimates.append(_compute_expectancy(sample))
        r_estimates.append(_compute_mean_r(sample))
        
    pf_estimates.sort()
    exp_estimates.sort()
    r_estimates.sort()
    
    alpha = 1.0 - config.bootstrap_confidence_level
    lower_idx = int(config.bootstrap_iterations * (alpha / 2.0))
    upper_idx = min(int(config.bootstrap_iterations * (1.0 - (alpha / 2.0))), config.bootstrap_iterations - 1)
    
    pf_ci = ConfidenceInterval(
        lower_bound=pf_estimates[lower_idx],
        upper_bound=pf_estimates[upper_idx],
        mean_estimate=_compute_pf(usable_records)
    )
    
    exp_ci = ConfidenceInterval(
        lower_bound=exp_estimates[lower_idx],
        upper_bound=exp_estimates[upper_idx],
        mean_estimate=_compute_expectancy(usable_records)
    )
    
    r_ci = ConfidenceInterval(
        lower_bound=r_estimates[lower_idx],
        upper_bound=r_estimates[upper_idx],
        mean_estimate=_compute_mean_r(usable_records)
    )
    
    # If the intervals are extremely wide or cross zero for expectancy, we might say LOW_CONFIDENCE
    # A simple heuristic: if lower_bound of expectancy < 0 and upper_bound > 0, we lack confidence it's strictly positive/negative.
    # But since the user wants us to determine if we have high or low confidence, let's say if it crosses zero it's LOW_CONFIDENCE for a "profitable" strategy, 
    # but since we just measure, if the range (upper - lower) is very large, it's low confidence.
    # Let's say if lower bound of expectancy < 0 and mean > 0, it's low confidence in positive expectancy.
    if exp_ci.lower_bound < 0 and exp_ci.mean_estimate > 0:
        status = SignificanceLevel.LOW_CONFIDENCE
    else:
        status = SignificanceLevel.HIGH_CONFIDENCE
        
    return BootstrapReport(
        status=status,
        expectancy_ci=exp_ci,
        profit_factor_ci=pf_ci,
        mean_r_ci=r_ci
    )
