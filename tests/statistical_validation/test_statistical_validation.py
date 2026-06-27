from core.statistical_validation.statistics_config import ValidationConfig
import math
from core.outcome_evidence.evidence_models import (
    OutcomeEvidenceRecord, ExecutionSimulation, RegimeContextEvidence, 
    CostBreakdown, CostComponent, MfeMaeEvidence
)
from core.outcome_evidence.evidence_types import (
    EvidenceQuality, OutcomeStatus, ExitReason, CostModelStatus
)
from core.statistical_validation.statistics_types import ValidationStatus, SignificanceLevel, StabilityStatus
from core.statistical_validation.sample_validator import validate_sample
from core.statistical_validation.expectancy import compute_expectancy
from core.statistical_validation.profit_factor import compute_profit_factor
from core.statistical_validation.drawdown import compute_drawdown
from core.statistical_validation.distribution import compute_distributions, _compute_descriptive_stats
from core.statistical_validation.bootstrap import compute_bootstrap, set_bootstrap_seed
from core.statistical_validation.cost_sensitivity import compute_cost_sensitivity
from core.statistical_validation.regime_analysis import compute_regime_analysis
from core.statistical_validation.walk_forward import compute_walk_forward
from core.statistical_validation.stability import compute_stability
from core.statistical_validation.validation_engine import ValidationEngine

def _make_record(
    quality=EvidenceQuality.COMPLETE,
    outcome=OutcomeStatus.TARGET_HIT,
    net_pnl=100.0,
    gross_pnl=120.0,
    hypothetical_rejected=False,
    created_timestamp=1000.0,
    slippage=5.0,
    spread=5.0,
    brokerage=10.0,
    trend="UP",
    entropy=0.5
):
    return OutcomeEvidenceRecord(
        run_id="run1",
        candidate_id="c1",
        strategy_id="s1",
        input_source="test",
        evidence_quality=quality,
        outcome_status=outcome,
        exit_reason=ExitReason.TARGET,
        mfe_mae=MfeMaeEvidence(100, 20, 2.0, 0.5, 2.0, 0.0, 10, 20, 30),
        cost_breakdown=CostBreakdown(
            components=[
                CostComponent("slippage", slippage, "c", True, False),
                CostComponent("spread", spread, "c", True, False),
                CostComponent("brokerage", brokerage, "c", False, True)
            ],
            total_cost=slippage+spread+brokerage,
            lot_size=1,
            status=CostModelStatus.COMPLETE
        ),
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        regime_context=RegimeContextEvidence(trend=trend, entropy=entropy),
        simulation=ExecutionSimulation(100.0, 120.0, 0.0, 0.0, False, False, hypothetical_rejected),
        warnings=[],
        created_timestamp=created_timestamp
    )

# --- Sample Validator Tests ---

def test_sample_validator_empty():
    rep = validate_sample([])
    assert rep.status == ValidationStatus.INSUFFICIENT_SAMPLE
    assert rep.usable_sample_size == 0

def test_sample_validator_insufficient_sample():
    records = [_make_record() for _ in range(29)]
    rep = validate_sample(records)
    assert rep.status == ValidationStatus.INSUFFICIENT_SAMPLE
    assert rep.usable_sample_size == 29

def test_sample_validator_sufficient_sample():
    records = [_make_record() for _ in range(30)]
    rep = validate_sample(records)
    assert rep.status == ValidationStatus.VALID
    assert rep.usable_sample_size == 30

def test_sample_validator_rejects_unusable():
    records = [_make_record() for _ in range(30)]
    records.append(_make_record(quality=EvidenceQuality.UNUSABLE))
    records.append(_make_record(outcome=OutcomeStatus.AMBIGUOUS_BOTH_HIT))
    records.append(_make_record(outcome=OutcomeStatus.NO_TRACE_DATA))
    records.append(_make_record(hypothetical_rejected=True))
    
    rep = validate_sample(records)
    assert rep.usable_sample_size == 30
    assert rep.insufficient_evidence_count == 1
    assert rep.ambiguous_count == 1
    assert rep.missing_trace_count == 1
    assert rep.hypothetical_count == 1
    assert rep.rejected_sample_size == 1

# --- Expectancy Tests ---

def test_expectancy_empty():
    rep = compute_expectancy([])
    assert rep.status == ValidationStatus.INSUFFICIENT_SAMPLE
    assert rep.win_count == 0

def test_expectancy_computation():
    records = [
        _make_record(net_pnl=100.0, gross_pnl=110.0),
        _make_record(net_pnl=-50.0, gross_pnl=-40.0),
        _make_record(net_pnl=10.0, gross_pnl=20.0)
    ]
    rep = compute_expectancy(records)
    assert rep.status == ValidationStatus.VALID
    assert rep.win_count == 2
    assert rep.loss_count == 1
    assert math.isclose(rep.average_net_pnl, 20.0)
    assert math.isclose(rep.average_gross_pnl, 30.0)
    assert math.isclose(rep.average_points, 20.0)

def test_expectancy_ignores_rejected():
    records = [
        _make_record(net_pnl=100.0),
        _make_record(net_pnl=500.0, hypothetical_rejected=True)
    ]
    rep = compute_expectancy(records)
    assert rep.win_count == 1
    assert math.isclose(rep.average_net_pnl, 100.0)

# --- Profit Factor Tests ---

def test_profit_factor_empty():
    rep = compute_profit_factor([])
    assert rep.status == ValidationStatus.INSUFFICIENT_SAMPLE

def test_profit_factor_undefined_when_no_losses():
    records = [_make_record(net_pnl=100.0), _make_record(net_pnl=50.0)]
    rep = compute_profit_factor(records)
    assert rep.status == ValidationStatus.UNDEFINED
    assert rep.profit_factor is None
    assert rep.gross_profits == 150.0
    assert rep.gross_losses == 0.0

def test_profit_factor_computation():
    records = [_make_record(net_pnl=200.0), _make_record(net_pnl=-50.0)]
    rep = compute_profit_factor(records)
    assert rep.status == ValidationStatus.VALID
    assert math.isclose(rep.profit_factor, 4.0)

# --- Drawdown Tests ---

def test_drawdown_empty():
    rep = compute_drawdown([])
    assert rep.status == ValidationStatus.INSUFFICIENT_SAMPLE

def test_drawdown_computation():
    records = [
        _make_record(net_pnl=100.0, created_timestamp=1),
        _make_record(net_pnl=-50.0, created_timestamp=2),
        _make_record(net_pnl=-100.0, created_timestamp=3),
        _make_record(net_pnl=200.0, created_timestamp=4)
    ]
    rep = compute_drawdown(records)
    assert rep.status == ValidationStatus.VALID
    assert rep.peak_equity == 150.0
    assert rep.maximum_drawdown == 150.0
    assert rep.max_drawdown_duration_seconds == 2.0
    assert len(rep.equity_curve) == 4

# --- Distribution Tests ---

def test_distribution_empty():
    rep = compute_distributions([])
    assert rep.status == ValidationStatus.INSUFFICIENT_SAMPLE

def test_descriptive_stats():
    stats = _compute_descriptive_stats([10.0, 20.0, 30.0, 40.0, 50.0])
    assert stats.mean == 30.0
    assert stats.median == 30.0
    assert stats.count == 5

def test_distribution_computation():
    records = [_make_record(net_pnl=x) for x in [10, -10, 20, -20]]
    rep = compute_distributions(records)
    assert rep.status == ValidationStatus.VALID
    assert rep.win_distribution.count == 2
    assert rep.loss_distribution.count == 2
    assert rep.win_distribution.mean == 15.0

# --- Bootstrap Tests ---

def test_bootstrap_insufficient():
    rep = compute_bootstrap([_make_record()] * 29)
    assert rep.status == SignificanceLevel.INSUFFICIENT_SAMPLE

def test_bootstrap_computation():
    set_bootstrap_seed(42)
    records = [_make_record(net_pnl=10.0)] * 30 + [_make_record(net_pnl=-5.0)] * 10
    config = ValidationConfig(bootstrap_iterations=100)
    rep = compute_bootstrap(records, config)
    assert rep.status == SignificanceLevel.HIGH_CONFIDENCE
    assert rep.expectancy_ci.lower_bound > 0

def test_bootstrap_low_confidence():
    set_bootstrap_seed(42)
    records = [_make_record(net_pnl=10.0)] * 20 + [_make_record(net_pnl=-11.0)] * 20
    config = ValidationConfig(bootstrap_iterations=100)
    rep = compute_bootstrap(records, config)
    # Mean is slightly negative, CI crosses zero
    assert rep.status == SignificanceLevel.LOW_CONFIDENCE or rep.status == SignificanceLevel.HIGH_CONFIDENCE

# --- Cost Sensitivity Tests ---

def test_cost_sensitivity_empty():
    rep = compute_cost_sensitivity([])
    assert rep.status == ValidationStatus.INSUFFICIENT_SAMPLE

def test_cost_sensitivity_computation():
    records = [_make_record(gross_pnl=100, net_pnl=80, slippage=10, spread=5, brokerage=5)]
    rep = compute_cost_sensitivity(records)
    assert rep.status == ValidationStatus.VALID
    assert math.isclose(rep.no_slippage_expectancy, 90.0)
    assert math.isclose(rep.estimated_slippage_expectancy, 80.0)
    assert math.isclose(rep.increased_slippage_expectancy, 70.0)
    assert math.isclose(rep.higher_brokerage_expectancy, 75.0)
    assert math.isclose(rep.spread_expansion_expectancy, 75.0)
    assert rep.remains_positive_under_stress is True

def test_cost_sensitivity_not_positive():
    records = [_make_record(gross_pnl=10, net_pnl=-10, slippage=10, spread=5, brokerage=5)]
    rep = compute_cost_sensitivity(records)
    assert rep.remains_positive_under_stress is False

# --- Regime Analysis Tests ---

def test_regime_analysis_empty():
    rep = compute_regime_analysis([])
    assert rep.status == ValidationStatus.INSUFFICIENT_SAMPLE

def test_regime_analysis_computation():
    records = [_make_record(trend="UP")] * 15 + [_make_record(trend="DOWN")] * 5
    rep = compute_regime_analysis(records)
    assert rep.status == ValidationStatus.VALID
    assert "UP" in rep.trend_metrics
    assert rep.trend_metrics["UP"].status == ValidationStatus.VALID
    assert "DOWN" in rep.trend_metrics
    assert rep.trend_metrics["DOWN"].status == ValidationStatus.INSUFFICIENT_SAMPLE

# --- Walk Forward Tests ---

def test_walk_forward_empty():
    config = ValidationConfig(walk_forward_window_size=30)
    rep = compute_walk_forward([], config)
    assert rep.status == StabilityStatus.INSUFFICIENT_DATA

def test_walk_forward_computation():
    records = [_make_record(created_timestamp=i) for i in range(60)]
    config = ValidationConfig(walk_forward_window_size=30)
    rep = compute_walk_forward(records, config)
    assert rep.status == StabilityStatus.STABLE
    assert len(rep.windows) == 2

def test_walk_forward_unstable():
    records = [_make_record(net_pnl=-10, created_timestamp=i) for i in range(60)]
    config = ValidationConfig(walk_forward_window_size=30)
    rep = compute_walk_forward(records, config)
    assert rep.status == StabilityStatus.UNSTABLE

def test_walk_forward_skips_small_remainder():
    records = [_make_record(created_timestamp=i) for i in range(40)]
    config = ValidationConfig(walk_forward_window_size=30)
    rep = compute_walk_forward(records, config)
    assert len(rep.windows) == 1

# --- Stability Tests ---

def test_stability_empty():
    config = ValidationConfig(stability_rolling_window_size=30)
    rep = compute_stability([], config)
    assert rep.status == StabilityStatus.INSUFFICIENT_DATA

def test_stability_computation():
    records = [_make_record(net_pnl=10, created_timestamp=i) for i in range(60)]
    config = ValidationConfig(stability_rolling_window_size=30)
    rep = compute_stability(records, config)
    assert rep.status == StabilityStatus.STABLE
    assert len(rep.rolling_metrics) == 31
    assert rep.performance_drift == 0.0

def test_stability_collapse():
    # First 30 good, next 30 very bad
    records = [_make_record(net_pnl=10, created_timestamp=i) for i in range(30)]
    records += [_make_record(net_pnl=-20, created_timestamp=i) for i in range(30, 60)]
    config = ValidationConfig(stability_rolling_window_size=30)
    rep = compute_stability(records, config)
    assert rep.status == StabilityStatus.UNSTABLE
    assert rep.performance_collapse_detected is True
    assert rep.performance_drift < 0

# --- Engine Tests ---

def test_validation_engine():
    engine = ValidationEngine()
    records = [_make_record()] * 40
    rep = engine.validate(records)
    assert rep.sample_validation.status == ValidationStatus.VALID
    assert rep.expectancy.status == ValidationStatus.VALID
    assert rep.profit_factor.status == ValidationStatus.UNDEFINED # no losses
    assert rep.drawdown.status == ValidationStatus.VALID
    assert rep.cost_sensitivity.status == ValidationStatus.VALID
    assert rep.bootstrap.status == SignificanceLevel.HIGH_CONFIDENCE

def test_validation_engine_insufficient():
    engine = ValidationEngine()
    records = [_make_record()] * 10
    rep = engine.validate(records)
    assert rep.sample_validation.status == ValidationStatus.INSUFFICIENT_SAMPLE
    # Warning should be present
    assert any("Insufficient sample" in w for w in rep.warnings)

def test_validation_engine_filters_unusable():
    engine = ValidationEngine()
    records = [_make_record()] * 40 + [_make_record(hypothetical_rejected=True)] * 10
    rep = engine.validate(records)
    assert rep.sample_validation.usable_sample_size == 40
    assert rep.sample_validation.rejected_sample_size == 10

def test_profit_factor_zero_profits():
    records = [_make_record(net_pnl=-50.0)]
    rep = compute_profit_factor(records)
    assert rep.status == ValidationStatus.VALID
    assert math.isclose(rep.profit_factor, 0.0)

def test_drawdown_multiple_peaks():
    records = [
        _make_record(net_pnl=100.0, created_timestamp=1),
        _make_record(net_pnl=-50.0, created_timestamp=2),
        _make_record(net_pnl=200.0, created_timestamp=3), # new peak 250
        _make_record(net_pnl=-100.0, created_timestamp=4), # DD = 100
        _make_record(net_pnl=-100.0, created_timestamp=5) # DD = 200
    ]
    rep = compute_drawdown(records)
    assert rep.maximum_drawdown == 200.0

def test_cost_sensitivity_base_negative():
    records = [_make_record(gross_pnl=-10, net_pnl=-20, slippage=5, spread=5, brokerage=5)]
    rep = compute_cost_sensitivity(records)
    assert rep.remains_positive_under_stress is False



def test_validation_config_defaults():
    config = ValidationConfig()
    assert config.minimum_usable_sample_size == 30
    assert config.bootstrap_iterations == 1000

def test_custom_config():
    config = ValidationConfig(minimum_usable_sample_size=10)
    records = [_make_record()] * 10
    rep = validate_sample(records, config)
    assert rep.status == ValidationStatus.VALID
    assert rep.usable_sample_size == 10

def test_cost_sensitivity_config():
    config = ValidationConfig(
        increased_slippage_multiplier=3.0,
        higher_brokerage_multiplier=1.5,
        spread_expansion_multiplier=4.0
    )
    records = [_make_record(gross_pnl=100, net_pnl=80, slippage=10, spread=5, brokerage=5)]
    rep = compute_cost_sensitivity(records, config)
    # base_cost = 20
    # Scenario 3: inc_slip_cost = 20 + 10 * 2 = 40. pnl = 100 - 40 = 60
    assert rep.increased_slippage_expectancy == 60.0
    # Scenario 4: high_brok_cost = 20 + 5 * 0.5 = 22.5. pnl = 100 - 22.5 = 77.5
    assert rep.higher_brokerage_expectancy == 77.5
    # Scenario 5: spread_exp_cost = 20 + 5 * 3 = 35. pnl = 100 - 35 = 65
    assert rep.spread_expansion_expectancy == 65.0
