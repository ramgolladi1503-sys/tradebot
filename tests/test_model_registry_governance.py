from __future__ import annotations

import json

from core import model_registry as reg
from core import ml_governance as gov


def test_validate_model_entry_rejects_missing_provenance():
    valid, reason = reg.validate_model_entry({"type": "xgb", "path": "models/a.pkl", "status": "active"})

    assert valid is False
    assert reason == "MODEL_ENTRY_MISSING_PROVENANCE"


def test_validate_model_entry_accepts_minimal_provenance():
    valid, reason = reg.validate_model_entry(
        {
            "type": "xgb",
            "path": "models/a.pkl",
            "status": "active",
            "hash": "abc123",
            "governance": {"features": ["x"], "training_window": {"rows": 10}},
        }
    )

    assert valid is True
    assert reason == "ok"


def test_validate_model_entry_rejects_low_regime_coverage():
    valid, reason = reg.validate_model_entry(
        {
            "type": "xgb",
            "path": "models/a.pkl",
            "hash": "abc123",
            "governance": {
                "features": ["x"],
                "training_window": {"rows": 10},
                "regime_coverage": {"TREND": 0.1, "RANGE": 0.9},
            },
        }
    )

    assert valid is False
    assert reason == "MODEL_ENTRY_INSUFFICIENT_REGIME_COVERAGE"


def test_select_walk_forward_model_chooses_best_admissible_candidate():
    candidates = [
        {
            "admitted": True,
            "governance": {"regime_coverage": {"TREND": 0.3, "RANGE": 0.3}},
            "metrics": {"val_loss": 0.4, "val_accuracy": 0.6},
        },
        {
            "admitted": True,
            "governance": {"regime_coverage": {"TREND": 0.5, "RANGE": 0.5}},
            "metrics": {"val_loss": 0.3, "val_accuracy": 0.55},
        },
    ]

    result = gov.select_walk_forward_model(candidates, min_regime_coverage=0.2)

    assert result["status"] == "SELECTED"
    assert result["selected"]["metrics"]["val_loss"] == 0.3


def test_select_walk_forward_model_rejects_tiny_regime_shards():
    candidates = [
        {
            "admitted": True,
            "governance": {
                "regime_coverage": {"TREND": 0.6, "RANGE": 0.4},
                "walk_forward": {"regime_splits": [{"regime": "TREND", "rows": 3}, {"regime": "RANGE", "rows": 2}]},
            },
            "metrics": {"val_loss": 0.2, "val_accuracy": 0.8},
        }
    ]

    result = gov.select_walk_forward_model(candidates, min_regime_coverage=0.2, min_regime_rows=5)

    assert result["status"] == "NO_ADMISSIBLE_MODEL"
