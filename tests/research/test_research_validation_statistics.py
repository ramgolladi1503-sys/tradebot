import math

import numpy as np
import pytest
from hypothesis import given, strategies as st

from core.research_validation.statistics import (
    benjamini_hochberg,
    bonferroni_rejections,
    cscv_probability_of_backtest_overfitting,
    deflated_sharpe_ratio,
    effective_rank,
    minimum_track_record_length,
    probabilistic_sharpe_ratio,
    sample_sharpe,
)


def test_sample_sharpe_matches_direct_calculation():
    returns = [0.01, -0.02, 0.03, 0.015, -0.005]
    expected = np.mean(returns) / np.std(returns, ddof=1)
    assert sample_sharpe(returns) == pytest.approx(expected)


@pytest.mark.parametrize("bad", [[1.0], [1.0, 1.0], [1.0, math.nan], [1.0, math.inf]])
def test_sample_sharpe_rejects_undefined_or_nonfinite_inputs(bad):
    with pytest.raises(ValueError):
        sample_sharpe(bad)


def test_psr_increases_for_same_shape_with_stronger_mean():
    base = np.array([-1.0, -0.5, 0.2, 0.4, 0.7, 1.2] * 20)
    weak = base * 0.01 + 0.0001
    strong = base * 0.01 + 0.003
    assert probabilistic_sharpe_ratio(strong) > probabilistic_sharpe_ratio(weak)


def test_psr_penalizes_serial_dependence_relative_to_independent_sequence():
    rng = np.random.default_rng(7)
    innovations = rng.normal(0.001, 0.01, 500)
    serial = np.empty_like(innovations)
    serial[0] = innovations[0]
    for i in range(1, len(serial)):
        serial[i] = 0.85 * serial[i - 1] + innovations[i]
    iid_like = rng.permutation(serial)
    # Same marginal observations, different ordering. Serial dependence must not improve confidence.
    assert probabilistic_sharpe_ratio(serial, max_lag=12) <= probabilistic_sharpe_ratio(iid_like, max_lag=12)


def test_minimum_track_record_is_infinite_when_observed_sharpe_not_above_benchmark():
    returns = [-0.02, -0.01, 0.0, 0.01, -0.01] * 20
    assert minimum_track_record_length(returns, benchmark_sharpe=0.5) == math.inf


def test_effective_rank_identity_equals_number_of_independent_trials():
    assert effective_rank(np.eye(5)) == pytest.approx(5.0)


def test_effective_rank_perfectly_correlated_matrix_is_one():
    assert effective_rank(np.ones((6, 6))) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "matrix",
    [
        [[1.0, 0.2]],
        [[1.0, 0.2], [0.1, 1.0]],
        [[1.0, 2.0], [2.0, 1.0]],
        [[1.0, math.nan], [math.nan, 1.0]],
    ],
)
def test_effective_rank_rejects_invalid_correlation_matrices(matrix):
    with pytest.raises(ValueError):
        effective_rank(matrix)


def test_dsr_falls_as_effective_search_size_grows():
    selected = np.array([-0.01, 0.01, 0.0, 0.02, 0.005, 0.012] * 80)
    trials = np.linspace(-0.1, 0.25, 100)
    low_search = deflated_sharpe_ratio(selected, trials, effective_trials=2)
    high_search = deflated_sharpe_ratio(selected, trials, effective_trials=100)
    assert high_search < low_search


def test_dsr_rejects_impossible_effective_trial_count():
    selected = [0.01, -0.01, 0.02] * 20
    trials = [0.1, 0.2, 0.3]
    with pytest.raises(ValueError):
        deflated_sharpe_ratio(selected, trials, effective_trials=0)


def test_bonferroni_is_stricter_than_uncorrected_threshold():
    p = [0.01, 0.02, 0.04, 0.8]
    assert bonferroni_rejections(p, alpha=0.05) == [True, False, False, False]


def test_bh_known_example_and_original_order_preserved():
    p = [0.04, 0.001, 0.02, 0.9]
    assert benjamini_hochberg(p, q=0.05) == [False, True, True, False]


@pytest.mark.parametrize("bad", [[], [-0.1], [1.1], [math.nan], [math.inf]])
def test_multiple_testing_rejects_invalid_p_values(bad):
    with pytest.raises(ValueError):
        bonferroni_rejections(bad)
    with pytest.raises(ValueError):
        benjamini_hochberg(bad)


def test_cscv_pbo_detects_deliberate_selection_instability():
    # Strategy 0 dominates the first half and collapses in the second; strategy 1 reverses it.
    first = np.column_stack([np.full(40, 0.02), np.full(40, -0.01)])
    second = np.column_stack([np.full(40, -0.02), np.full(40, 0.01)])
    # Add tiny deterministic variation so Sharpe is finite.
    jitter = np.linspace(-1e-4, 1e-4, 80)[:, None]
    matrix = np.vstack([first, second]) + np.hstack([jitter, -jitter])
    pbo = cscv_probability_of_backtest_overfitting(matrix, blocks=8)
    assert 0.5 <= pbo <= 1.0


def test_cscv_rejects_bad_shape_nonfinite_and_bad_blocks():
    with pytest.raises(ValueError):
        cscv_probability_of_backtest_overfitting([[0.1], [0.2], [0.3], [0.4]])
    with pytest.raises(ValueError):
        cscv_probability_of_backtest_overfitting([[0.1, 0.2], [0.2, math.nan], [0.3, 0.4], [0.4, 0.5]])
    matrix = np.arange(40, dtype=float).reshape(20, 2)
    with pytest.raises(ValueError):
        cscv_probability_of_backtest_overfitting(matrix, blocks=3)


@given(
    st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=40,
    )
)
def test_bh_never_rejects_a_pvalue_larger_than_its_selected_cutoff(p_values):
    decisions = benjamini_hochberg(p_values, q=0.1)
    rejected = [p for p, decision in zip(p_values, decisions) if decision]
    accepted = [p for p, decision in zip(p_values, decisions) if not decision]
    if rejected and accepted:
        assert max(rejected) <= min(accepted)


@given(st.integers(min_value=2, max_value=20))
def test_effective_rank_identity_property(n):
    assert effective_rank(np.eye(n)) == pytest.approx(float(n), rel=1e-10, abs=1e-10)
