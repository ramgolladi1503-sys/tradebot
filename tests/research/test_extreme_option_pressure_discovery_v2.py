from __future__ import annotations

import pandas as pd

from scripts.run_extreme_option_pressure_discovery_v2 import (
    MECHANISMS,
    calculate_metrics,
    expanding_folds,
)


def test_exact_theory_led_mechanism_budget() -> None:
    assert len(MECHANISMS) == 12
    assert len(set(MECHANISMS)) == 12


def test_expanding_folds_are_strictly_chronological() -> None:
    sessions = [f"2026-01-{day:02d}" for day in range(1, 21)]
    folds = expanding_folds(sessions)
    assert len(folds) == 4
    previous_training_size = 0
    observed_tests: list[str] = []
    for training, testing, fold_id in folds:
        assert fold_id.startswith("fold_")
        assert set(training).isdisjoint(testing)
        assert max(training) < min(testing)
        assert len(training) > previous_training_size
        previous_training_size = len(training)
        observed_tests.extend(testing)
    assert observed_tests == sessions[8:]


def test_metrics_fail_to_hide_two_winner_dependence() -> None:
    returns = [20.0, 18.0, 0.5, -3.0, -3.0, -3.0, -3.0, -3.0, -3.0, -3.0, -3.0, -3.0]
    frame = pd.DataFrame(
        {
            "fold_id": ["fold_1"] * 3 + ["fold_2"] * 3 + ["fold_3"] * 3 + ["fold_4"] * 3,
            "net_return_pct": returns,
            "stress_return_pct": [value - 0.9 for value in returns],
        }
    )
    metrics = calculate_metrics(frame)
    assert metrics.profit_factor is not None and metrics.profit_factor > 1.0
    assert metrics.remove_top_two_profit_factor is not None and metrics.remove_top_two_profit_factor < 1.0
    assert metrics.largest_winner_share is not None and metrics.largest_winner_share > 0.5
