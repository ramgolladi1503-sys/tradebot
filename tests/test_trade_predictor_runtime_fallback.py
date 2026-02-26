from __future__ import annotations

import pandas as pd
from sklearn.dummy import DummyClassifier

from ml import trade_predictor as tp


def test_trade_predictor_falls_back_to_dummy_when_xgb_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(tp, "_XGBClassifier", None, raising=False)
    monkeypatch.setattr(tp, "_XGB_IMPORT_ERROR", "XGBoostError:libomp_missing", raising=False)
    monkeypatch.setattr(tp, "get_active_entry", lambda _kind: None)
    monkeypatch.setattr(tp, "get_shadow_entry", lambda _kind: None)

    predictor = tp.TradePredictor(model_path=str(tmp_path / "missing_model.pkl"), load_existing=False)
    model = predictor.models.get("GLOBAL")

    assert predictor.xgb_available is False
    assert predictor.model_runtime == "dummy"
    assert isinstance(model, DummyClassifier)
    assert predictor.predict_confidence(pd.DataFrame([{"feature_a": 1.0}])) == 0.5


def test_trade_predictor_load_failure_degrades_without_crash(monkeypatch, tmp_path):
    bad_model = tmp_path / "bad_model.pkl"
    bad_model.write_bytes(b"not-a-joblib-model")
    monkeypatch.setattr(tp, "get_active_entry", lambda _kind: None)
    monkeypatch.setattr(tp, "get_shadow_entry", lambda _kind: None)

    predictor = tp.TradePredictor(model_path=str(bad_model), load_existing=True)
    assert "GLOBAL" in predictor.models
