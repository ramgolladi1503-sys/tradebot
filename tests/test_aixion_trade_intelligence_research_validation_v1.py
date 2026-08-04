from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aixion_trade_intelligence.research_validation import (
    TimedSample,
    deflated_sharpe_probability,
    probability_of_backtest_overfitting,
    purged_embargo_split,
)


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_purged_split_removes_overlapping_labels_and_embargoes_following_samples():
    samples = (
        TimedSample("train", BASE, BASE + timedelta(minutes=5)),
        TimedSample("overlap", BASE + timedelta(minutes=9), BASE + timedelta(minutes=12)),
        TimedSample("validation", BASE + timedelta(minutes=10), BASE + timedelta(minutes=11)),
        TimedSample("embargo", BASE + timedelta(minutes=21), BASE + timedelta(minutes=22)),
        TimedSample("later", BASE + timedelta(minutes=40), BASE + timedelta(minutes=41)),
    )
    result = purged_embargo_split(
        samples,
        validation_start=BASE + timedelta(minutes=10),
        validation_end=BASE + timedelta(minutes=20),
        embargo=timedelta(minutes=5),
    )
    assert result.train_ids == ("train", "later")
    assert result.validation_ids == ("validation",)
    assert result.purged_ids == ("overlap",)
    assert result.embargoed_ids == ("embargo",)


def test_deflated_sharpe_uses_explicit_trial_count_and_dispersion():
    result = deflated_sharpe_probability(
        [0.01, 0.02, -0.005, 0.015, 0.01, -0.002, 0.012, 0.006],
        independent_trials=10,
        trial_sharpe_std=0.2,
        annualization_factor=252.0,
    )
    assert result["observed_sharpe"] > 0
    assert result["deflated_benchmark_sharpe"] > 0
    assert 0.0 <= result["deflated_sharpe_probability"] <= 1.0


def test_pbo_flags_selection_that_does_not_rank_well_out_of_sample():
    result = probability_of_backtest_overfitting(
        [
            [10.0, 1.0],
            [10.0, 1.0],
            [-10.0, 1.0],
            [-10.0, 1.0],
        ]
    )
    assert result.combinations == 6
    assert result.overfit_combinations > 0
    assert 0.0 < result.probability_backtest_overfitting <= 1.0


def test_pbo_rejects_too_few_slices():
    with pytest.raises(ValueError, match="at_least_four"):
        probability_of_backtest_overfitting([[1.0, 2.0], [2.0, 1.0]])
