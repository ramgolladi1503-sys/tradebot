from __future__ import annotations

import pandas as pd

from config import config as cfg
from core.retrain_manager import RetrainManager


def test_retrain_trigger_when_rolling_metrics_breach(monkeypatch):
    monkeypatch.setattr(cfg, "ML_RETRAIN_ROLLING_WINDOW", 20, raising=False)
    monkeypatch.setattr(cfg, "ML_RETRAIN_MIN_WIN_RATE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "ML_RETRAIN_MIN_EXPECTANCY", 0.0, raising=False)
    monkeypatch.setattr(cfg, "ML_RETRAIN_MAX_ROLLING_DRAWDOWN", -0.01, raising=False)
    manager = RetrainManager()
    df = pd.DataFrame(
        {
            "actual": [0] * 20,
            "pnl": [-10.0] * 20,
        }
    )
    result = manager.evaluate_retrain_trigger(df, emit_incident=False)
    assert result.retrain_required is True
    assert "RETRAIN_TRIGGER:ROLLING_WIN_RATE_LOW" in result.reason_codes
    assert "RETRAIN_TRIGGER:NEGATIVE_EXPECTANCY" in result.reason_codes


def test_promotion_gate_rejects_worse_model(monkeypatch):
    monkeypatch.setattr(cfg, "ML_PROMOTION_MIN_RETURN_DELTA", 0.01, raising=False)
    monkeypatch.setattr(cfg, "ML_PROMOTION_MAX_DRAWDOWN_WORSEN", 0.0, raising=False)
    monkeypatch.setattr(cfg, "ML_PROMOTION_REQUIRE_ABLATION_SAFETY", True, raising=False)
    manager = RetrainManager()
    result = manager.evaluate_promotion_gate(
        champion_metrics={"acc": 0.55},
        challenger_metrics={"acc": 0.60},
        walk_forward_metrics={
            "champion_return": 0.10,
            "challenger_return": 0.05,
            "champion_max_drawdown": -0.05,
            "challenger_max_drawdown": -0.08,
        },
        ablation_report={
            "baseline": {"return": 0.10, "max_drawdown": -0.05},
            "ablations": [{"name": "use_ml_off", "return": 0.09, "max_drawdown": -0.04}],
        },
    )
    assert result.allowed is False
    assert result.reason_code == "MODEL_PROMOTE_REJECT:WALK_FORWARD_RETURN_NOT_IMPROVED"


def test_promotion_gate_allows_better_model(monkeypatch):
    monkeypatch.setattr(cfg, "ML_PROMOTION_MIN_RETURN_DELTA", 0.01, raising=False)
    monkeypatch.setattr(cfg, "ML_PROMOTION_MAX_DRAWDOWN_WORSEN", 0.0, raising=False)
    monkeypatch.setattr(cfg, "ML_PROMOTION_REQUIRE_ABLATION_SAFETY", True, raising=False)
    manager = RetrainManager()
    result = manager.evaluate_promotion_gate(
        champion_metrics={"acc": 0.55},
        challenger_metrics={"acc": 0.60},
        walk_forward_metrics={
            "champion_return": 0.05,
            "challenger_return": 0.08,
            "champion_max_drawdown": -0.08,
            "challenger_max_drawdown": -0.07,
        },
        ablation_report={
            "baseline": {"return": 0.10, "max_drawdown": -0.05},
            "ablations": [{"name": "use_trailing_sl_off", "return": 0.08, "max_drawdown": -0.06}],
        },
    )
    assert result.allowed is True
    assert result.reason_code == "MODEL_PROMOTE_OK"

