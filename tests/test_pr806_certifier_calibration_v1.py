from __future__ import annotations

import numpy as np

from research.pr806_certifier_calibration_v1.calibration import (
    asymmetric_payoff_control,
    bh_qvalues,
)


def test_bh_qvalues_matches_standard_monotone_adjustment() -> None:
    q = bh_qvalues([0.01, 0.04, 0.03, 0.20])
    assert np.allclose(q, [0.04, 0.05333333333333334, 0.05333333333333334, 0.20])


def test_asymmetric_positive_expectancy_is_not_equivalent_to_hit_rate_edge() -> None:
    control = asymmetric_payoff_control()
    assert control["mean_bps"] == 5.0
    assert control["hit_rate"] == 0.40
    assert control["current_hit_rate_gate_ge_55pct"] is False
    assert control["current_sign_p"] > 0.95
    assert control["mean_targeting_bootstrap_p"] < 0.01


def test_empty_bh_input_is_supported() -> None:
    q = bh_qvalues([])
    assert q.size == 0
