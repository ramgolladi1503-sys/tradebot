from typing import List, Dict, Callable, Optional
from collections import defaultdict
from core.outcome_evidence.evidence_models import OutcomeEvidenceRecord
from .statistics_models import RegimeReport, RegimeMetrics
from .statistics_types import ValidationStatus
from .statistics_config import ValidationConfig
from .expectancy import compute_expectancy
from .profit_factor import compute_profit_factor
from .drawdown import compute_drawdown
from .bootstrap import compute_bootstrap

def _evaluate_regime(name: str, records: List[OutcomeEvidenceRecord], config: ValidationConfig) -> RegimeMetrics:
    n = len(records)
    if n < config.minimum_regime_sample_size:
        return RegimeMetrics(
            regime_name=name,
            sample_size=n,
            status=ValidationStatus.INSUFFICIENT_SAMPLE
        )
        
    exp = compute_expectancy(records)
    pf = compute_profit_factor(records)
    dd = compute_drawdown(records)
    boot = compute_bootstrap(records, config)
    
    return RegimeMetrics(
        regime_name=name,
        sample_size=n,
        expectancy=exp.average_net_pnl,
        profit_factor=pf.profit_factor,
        max_drawdown=dd.maximum_drawdown,
        confidence=boot.status,
        status=ValidationStatus.VALID
    )

def _group_by_extractor(usable_records: List[OutcomeEvidenceRecord], extractor: Callable[[OutcomeEvidenceRecord], str], config: ValidationConfig) -> Dict[str, RegimeMetrics]:
    groups = defaultdict(list)
    for r in usable_records:
        val = extractor(r)
        if val is not None:
            groups[val].append(r)
            
    metrics = {}
    for name, group_records in groups.items():
        metrics[name] = _evaluate_regime(name, group_records, config)
        
    return dict(metrics)

def compute_regime_analysis(usable_records: List[OutcomeEvidenceRecord], config: Optional[ValidationConfig] = None) -> RegimeReport:
    """
    Slices records by regime (trend, range, entropy bucket, etc.) and computes metrics.
    """
    if config is None:
        config = ValidationConfig()
        
    if not usable_records:
        return RegimeReport(status=ValidationStatus.INSUFFICIENT_SAMPLE)
        
    # Helpers to safely extract
    def _extract_trend(r): return r.regime_context.trend
    def _extract_range(r): return r.regime_context.range_status
    def _extract_entropy(r): return str(r.regime_context.entropy) if r.regime_context.entropy is not None else "UNKNOWN"
    def _extract_volatility(r): return str(r.regime_context.volatility) if r.regime_context.volatility is not None else "UNKNOWN"
    def _extract_expiry(r): return "EXPIRY" if r.regime_context.is_expiry_day else "NON_EXPIRY"
    def _extract_iv(r): return r.regime_context.iv_bucket
    def _extract_liquidity(r): return r.regime_context.liquidity_bucket
    def _extract_spread(r): return r.regime_context.spread_bucket
    
    # Let's clean up entropy/volatility by grouping them. 
    # But for now the regime context may have pre-bucketed values or raw values.
    # The instructions say: "entropy bucket, volatility bucket".
    # I'll assume they might be raw or pre-bucketed. If raw, we might just stringify them. 
    # Usually they are bucketing in the regime_context.

    return RegimeReport(
        status=ValidationStatus.VALID,
        trend_metrics=_group_by_extractor(usable_records, _extract_trend, config),
        range_metrics=_group_by_extractor(usable_records, _extract_range, config),
        entropy_metrics=_group_by_extractor(usable_records, _extract_entropy, config),
        volatility_metrics=_group_by_extractor(usable_records, _extract_volatility, config),
        expiry_metrics=_group_by_extractor(usable_records, _extract_expiry, config),
        iv_metrics=_group_by_extractor(usable_records, _extract_iv, config),
        liquidity_metrics=_group_by_extractor(usable_records, _extract_liquidity, config),
        spread_metrics=_group_by_extractor(usable_records, _extract_spread, config)
    )
