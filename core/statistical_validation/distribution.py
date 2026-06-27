import math
from typing import List
from core.outcome_evidence.evidence_models import OutcomeEvidenceRecord
from .statistics_models import DistributionReport, DescriptiveStats
from .statistics_types import ValidationStatus

def _compute_descriptive_stats(values: List[float]) -> DescriptiveStats:
    n = len(values)
    if n == 0:
        return DescriptiveStats(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        
    sorted_vals = sorted(values)
    mean = sum(sorted_vals) / n
    
    if n % 2 == 0:
        median = (sorted_vals[n//2 - 1] + sorted_vals[n//2]) / 2.0
    else:
        median = sorted_vals[n//2]
        
    variance = sum((x - mean) ** 2 for x in sorted_vals) / n if n > 1 else 0.0
    std_dev = math.sqrt(variance)
    
    def percentile(p: float) -> float:
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_vals[int(k)]
        d0 = sorted_vals[int(f)] * (c - k)
        d1 = sorted_vals[int(c)] * (k - f)
        return d0 + d1

    return DescriptiveStats(
        count=n,
        mean=mean,
        median=median,
        variance=variance,
        standard_deviation=std_dev,
        percentile_5=percentile(0.05),
        percentile_25=percentile(0.25),
        percentile_75=percentile(0.75),
        percentile_95=percentile(0.95)
    )

def compute_distributions(usable_records: List[OutcomeEvidenceRecord]) -> DistributionReport:
    if not usable_records:
        return DistributionReport(status=ValidationStatus.INSUFFICIENT_SAMPLE)
        
    wins = [r.net_pnl for r in usable_records if r.net_pnl > 0]
    losses = [r.net_pnl for r in usable_records if r.net_pnl < 0]
    
    rs = [r.mfe_mae.realized_r for r in usable_records if r.mfe_mae is not None]
    durations = [r.mfe_mae.hold_duration for r in usable_records if r.mfe_mae is not None]
    
    mfes = [r.mfe_mae.mfe_r for r in usable_records if r.mfe_mae is not None]
    maes = [r.mfe_mae.mae_r for r in usable_records if r.mfe_mae is not None]
    
    return DistributionReport(
        status=ValidationStatus.VALID,
        win_distribution=_compute_descriptive_stats(wins) if wins else None,
        loss_distribution=_compute_descriptive_stats(losses) if losses else None,
        r_distribution=_compute_descriptive_stats(rs) if rs else None,
        duration_distribution=_compute_descriptive_stats(durations) if durations else None,
        mfe_distribution=_compute_descriptive_stats(mfes) if mfes else None,
        mae_distribution=_compute_descriptive_stats(maes) if maes else None
    )
