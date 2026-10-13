import math
from statistics import NormalDist
from unittest.mock import patch

import numpy as np
import pytest

import core.research_validation.statistics as stats


def test_dsr_uses_published_zero_mean_selection_threshold_not_trial_mean_shift():
    selected = np.array([-0.01, 0.01, 0.0, 0.02, 0.005, 0.012] * 80)
    trials = np.array([-0.4, -0.1, 0.2, 0.7, 1.3], dtype=float)
    n = float(len(trials))
    gamma = 0.5772156649015329
    normal = NormalDist()
    expected_max_z = (
        (1.0 - gamma) * normal.inv_cdf(1.0 - 1.0 / n)
        + gamma * normal.inv_cdf(1.0 - 1.0 / (n * math.e))
    )
    published_sr0 = float(np.std(trials, ddof=1)) * expected_max_z
    expected = stats.probabilistic_sharpe_ratio(selected, benchmark_sharpe=published_sr0)
    actual = stats.deflated_sharpe_ratio(selected, trials, effective_trials=n)
    assert actual == pytest.approx(expected, rel=1e-12, abs=1e-12)

    # Regression guard: the previously implemented extra +mean(trials) term must not return the same result.
    wrong_sr0 = float(np.mean(trials)) + published_sr0
    wrong = stats.probabilistic_sharpe_ratio(selected, benchmark_sharpe=wrong_sr0)
    assert actual != pytest.approx(wrong, rel=1e-8, abs=1e-8)


def test_cscv_enumerates_all_s_choose_s_over_2_train_test_combinations():
    rng = np.random.default_rng(42)
    matrix = rng.normal(0.001, 0.01, size=(80, 6))
    original = stats._column_sharpes
    calls = 0

    def counted(matrix_arg):
        nonlocal calls
        calls += 1
        return original(matrix_arg)

    with patch.object(stats, "_column_sharpes", side_effect=counted):
        result = stats.cscv_probability_of_backtest_overfitting(matrix, blocks=4)

    assert 0.0 <= result <= 1.0
    # One train score vector + one test score vector for each C(4,2)=6 combination.
    assert calls == 2 * math.comb(4, 2)


def test_cscv_requires_equal_sized_contiguous_partitions():
    rng = np.random.default_rng(1)
    matrix = rng.normal(0.0, 1.0, size=(82, 4))
    with pytest.raises(ValueError, match="equal-sized"):
        stats.cscv_probability_of_backtest_overfitting(matrix, blocks=8)


def test_cscv_refuses_to_silently_drop_undefined_strategy_statistics():
    rng = np.random.default_rng(9)
    variable = rng.normal(0.001, 0.01, size=80)
    constant = np.ones(80)
    matrix = np.column_stack([variable, constant])
    with pytest.raises(ValueError, match="all strategy performance statistics"):
        stats.cscv_probability_of_backtest_overfitting(matrix, blocks=8)
