from __future__ import annotations

from research.opening_dislocation_reversal.fresh_epoch_acquisition import classify_prior_use


def test_prior_outcome_dates_are_excluded_exactly():
    prior = {"20230102", "20240701"}
    assert classify_prior_use("2023-01-02", prior) == "PRIOR_OUTCOME_USED"
    assert classify_prior_use("2024-07-01", prior) == "PRIOR_OUTCOME_USED"
    assert classify_prior_use("2022-12-30", prior) == "ELIGIBLE_FOR_DATA_VALIDATION"
