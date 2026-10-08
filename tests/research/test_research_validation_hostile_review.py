import math

import numpy as np
import pytest

from core.research_validation.policy import BLOCKED, CertificationInput, certify_research
from core.research_validation.statistics import (
    benjamini_hochberg,
    bonferroni_rejections,
    cscv_probability_of_backtest_overfitting,
    deflated_sharpe_ratio,
    minimum_track_record_length,
    probabilistic_sharpe_ratio,
)


def _good(**overrides):
    data = dict(
        hypothesis_id="H1",
        registered_experiments=10,
        declared_experiments=10,
        parameter_stability_pass=True,
        wfa_pass=True,
        pbo=0.1,
        psr=0.99,
        dsr=0.99,
        actual_track_record=500,
        minimum_track_record=100,
        power=0.9,
        cost_robust_pass=True,
        holdout_status="PASS",
        prospective_status="PASS",
        inference_model_valid=True,
        search_history_complete=True,
    )
    data.update(overrides)
    return CertificationInput(**data)


@pytest.mark.parametrize("field", ["pbo", "psr", "dsr", "power"])
def test_boolean_cannot_masquerade_as_probability(field):
    verdict = certify_research(_good(**{field: True}))
    assert verdict.status == BLOCKED


@pytest.mark.parametrize("field", ["registered_experiments", "declared_experiments", "actual_track_record"])
def test_boolean_cannot_masquerade_as_integer_count(field):
    verdict = certify_research(_good(**{field: True}))
    assert verdict.status == BLOCKED


@pytest.mark.parametrize("field", ["parameter_stability_pass", "wfa_pass", "cost_robust_pass", "inference_model_valid", "search_history_complete"])
def test_truthy_strings_cannot_masquerade_as_boolean_flags(field):
    verdict = certify_research(_good(**{field: "false"}))
    assert verdict.status == BLOCKED


def test_truthy_string_additional_gate_cannot_pass():
    verdict = certify_research(_good(additional_gates={"leakage": "false"}))
    assert verdict.status == BLOCKED
    assert "INVALID_ADDITIONAL_GATE" in verdict.reasons


@pytest.mark.parametrize("kwargs", [
    {"max_pbo": 1.0},
    {"min_psr": 0.0},
    {"min_dsr": 0.0},
    {"min_power": 0.0},
])
def test_policy_thresholds_cannot_be_weakened_by_caller(kwargs):
    verdict = certify_research(_good(), **kwargs)
    assert verdict.status == BLOCKED
    assert "POLICY_THRESHOLD_OVERRIDE_FORBIDDEN" in verdict.reasons


@pytest.mark.parametrize("status", ["pass", "TRUE", "", None, 1])
def test_holdout_status_requires_exact_governed_enum(status):
    verdict = certify_research(_good(holdout_status=status))
    assert verdict.status == BLOCKED


@pytest.mark.parametrize("status", ["pass", "TRUE", "", None, 1])
def test_prospective_status_requires_exact_governed_enum(status):
    verdict = certify_research(_good(prospective_status=status))
    assert verdict.status == BLOCKED


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, True])
def test_psr_rejects_nonfinite_or_boolean_benchmark(bad):
    with pytest.raises(ValueError):
        probabilistic_sharpe_ratio([0.01, -0.005, 0.02, 0.01], benchmark_sharpe=bad)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, True])
def test_mintrl_rejects_nonfinite_or_boolean_benchmark(bad):
    with pytest.raises(ValueError):
        minimum_track_record_length([0.01, -0.005, 0.02, 0.01], benchmark_sharpe=bad)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.1, math.nan, True])
def test_bonferroni_rejects_invalid_alpha(bad):
    with pytest.raises(ValueError):
        bonferroni_rejections([0.01, 0.02], alpha=bad)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.1, math.nan, True])
def test_bh_rejects_invalid_q(bad):
    with pytest.raises(ValueError):
        benjamini_hochberg([0.01, 0.02], q=bad)


@pytest.mark.parametrize("bad", [[True, 0.1], ["0.01", 0.1]])
def test_multiple_testing_rejects_coerced_pvalues(bad):
    with pytest.raises(ValueError):
        bonferroni_rejections(bad)
    with pytest.raises(ValueError):
        benjamini_hochberg(bad)


def test_dsr_rejects_effective_trials_above_raw_trial_count():
    with pytest.raises(ValueError):
        deflated_sharpe_ratio([0.01, -0.01, 0.02] * 20, [0.1, 0.2, 0.3], effective_trials=4)


def test_dsr_rejects_zero_variance_trial_sharpe_distribution():
    with pytest.raises(ValueError):
        deflated_sharpe_ratio([0.01, -0.01, 0.02] * 20, [0.2, 0.2, 0.2])


@pytest.mark.parametrize("blocks", [True, 4.0, 3, -4, 0])
def test_cscv_rejects_noninteger_odd_or_invalid_blocks(blocks):
    matrix = np.arange(80, dtype=float).reshape(40, 2)
    with pytest.raises(ValueError):
        cscv_probability_of_backtest_overfitting(matrix, blocks=blocks)


def test_cscv_rejects_all_constant_strategy_family():
    matrix = np.ones((80, 3), dtype=float)
    with pytest.raises(ValueError):
        cscv_probability_of_backtest_overfitting(matrix, blocks=8)


def test_certification_never_grants_execution_authority_even_on_pass():
    verdict = certify_research(_good())
    assert verdict.status == "CERTIFIED_RESEARCH"
    assert verdict.read_only is True
    assert verdict.is_order_action is False
    assert verdict.broker_api_called is False
    assert verdict.allowed_for_live_execution is False
    assert verdict.append is False
