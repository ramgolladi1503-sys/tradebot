from __future__ import annotations

from config import config as cfg
from core.contextual_thresholds import get_contextual_threshold_delta


def test_contextual_threshold_delta_is_zero_without_recommendation():
    assert (
        get_contextual_threshold_delta(
            "trigger",
            "continuation",
            "MIDDAY",
            "TRENDING",
            {},
        )
        == 0.0
    )


def test_contextual_threshold_delta_is_small_and_bounded(monkeypatch):
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_TUNING_MAX_DELTA", 0.03, raising=False)
    recommendations = {
        "recommended_contextual_adjustments": {
            "trigger|continuation|MIDDAY|TRENDING": {
                "recommended_delta": -0.08,
            }
        }
    }

    delta = get_contextual_threshold_delta(
        "trigger",
        "continuation",
        "MIDDAY",
        "TRENDING",
        recommendations,
    )

    assert delta == -0.03


def test_contextual_threshold_delta_never_applies_to_protected_risk_gate():
    recommendations = {
        "protected_gate_map": {
            "risk_budget|continuation": {
                "gate_protected_flag": True,
            }
        },
        "recommended_contextual_adjustments": {
            "risk_budget|continuation|MIDDAY|TRENDING": {
                "recommended_delta": -0.02,
            }
        },
    }

    delta = get_contextual_threshold_delta(
        "risk_budget",
        "continuation",
        "MIDDAY",
        "TRENDING",
        recommendations,
    )

    assert delta == 0.0
