from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.audit_late_day_ce_inventory_rebound_v7_friction import (
    calculate_metrics,
    control_gate,
    holdout_gate,
    oof_gate,
    profit_factor,
)


def test_profit_factor_handles_all_positive_values() -> None:
    assert profit_factor([1.0, 2.0, 3.0]) == float("inf")


def test_cost_is_deducted_from_gross_premium_return() -> None:
    frame = pd.DataFrame(
        {
            "gross_5m_pct": [5.0, -1.0],
            "fold_id": ["fold_1", "fold_1"],
        }
    )

    metric = calculate_metrics(frame, 2.0)

    assert metric.mean_return_pct == pytest.approx(0.0)
    assert metric.net_return_pct_sum == pytest.approx(0.0)
    assert metric.profit_factor == pytest.approx(1.0)


def test_two_percent_oof_gate_requires_distributed_survival() -> None:
    per_fold_gross = np.asarray(([6.0] * 8) + ([0.0] * 2), dtype=float)
    frame = pd.DataFrame(
        {
            "gross_5m_pct": np.tile(per_fold_gross, 4),
            "fold_id": np.repeat(
                ["fold_1", "fold_2", "fold_3", "fold_4"], 10
            ),
        }
    )

    metric = calculate_metrics(frame, 2.0)

    assert metric.positive_folds == 4
    assert metric.remove_top_two_profit_factor is not None
    assert oof_gate(metric) is True


def test_holdout_gate_rejects_top_winner_dependence() -> None:
    frame = pd.DataFrame(
        {
            "gross_5m_pct": [50.0] + ([-1.0] * 11),
            "fold_id": ["holdout"] * 12,
        }
    )

    metric = calculate_metrics(frame, 2.0)

    assert metric.largest_winner_share is not None
    assert metric.largest_winner_share > 0.40
    assert holdout_gate(metric) is False


def test_control_gate_requires_mirror_loss_and_delayed_profit() -> None:
    primary = calculate_metrics(
        pd.DataFrame(
            {
                "gross_5m_pct": [6.0] * 12,
                "fold_id": ["holdout"] * 12,
            }
        ),
        2.0,
    )
    mirror = calculate_metrics(
        pd.DataFrame(
            {
                "gross_5m_pct": [0.0] * 12,
                "fold_id": ["holdout"] * 12,
            }
        ),
        2.0,
    )
    delayed = calculate_metrics(
        pd.DataFrame(
            {
                "gross_5m_pct": [4.0] * 12,
                "fold_id": ["holdout"] * 12,
            }
        ),
        2.0,
    )

    assert control_gate(primary, mirror, delayed) is True
