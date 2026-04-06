from __future__ import annotations

import pandas as pd
from sklearn.dummy import DummyClassifier

from config import config as cfg
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
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD", False, raising=False)

    predictor = tp.TradePredictor(model_path=str(bad_model), load_existing=True)
    assert "GLOBAL" in predictor.models


def test_trade_predictor_nonlive_startup_skips_persisted_model_load(monkeypatch, tmp_path):
    model_path = tmp_path / "xgb_live_model.pkl"
    model_path.write_bytes(b"placeholder")
    events = []

    def _fail_if_called(self, path):
        raise AssertionError(f"load should be skipped for non-live startup: {path}")

    monkeypatch.setattr(tp, "get_active_entry", lambda _kind: None)
    monkeypatch.setattr(tp, "get_shadow_entry", lambda _kind: None)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD", True, raising=False)
    monkeypatch.setattr(tp.TradePredictor, "load", _fail_if_called, raising=False)
    monkeypatch.setattr(tp, "append_runtime_event", lambda event_type, payload: events.append((event_type, dict(payload))))

    predictor = tp.TradePredictor(model_path=str(model_path), load_existing=True)

    assert predictor.model_runtime == "dummy"
    assert predictor.xgb_available is False
    assert isinstance(predictor.models.get("GLOBAL"), DummyClassifier)
    assert predictor.meta.get("degraded_reason") == "nonlive_startup_skip_persisted_model_load"
    assert events
    assert events[0][0] == "predictor_degraded_startup"
    assert events[0][1]["execution_mode"] == "SIM"


def test_trade_predictor_live_startup_still_uses_persisted_model_load(monkeypatch, tmp_path):
    model_path = tmp_path / "xgb_live_model.pkl"
    model_path.write_bytes(b"placeholder")
    load_calls = []

    def _fake_load(self, path):
        load_calls.append(path)
        self.models = {"GLOBAL": DummyClassifier(strategy="prior")}
        self.feature_list = None
        self.meta = {"loaded_via_test": True}

    monkeypatch.setattr(tp, "get_active_entry", lambda _kind: None)
    monkeypatch.setattr(tp, "get_shadow_entry", lambda _kind: None)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD", True, raising=False)
    monkeypatch.setattr(tp.TradePredictor, "load", _fake_load, raising=False)

    predictor = tp.TradePredictor(model_path=str(model_path), load_existing=True)

    assert load_calls == [str(model_path)]
    assert predictor.meta.get("loaded_via_test") is True


def test_trade_predictor_live_startup_safe_mode_skips_persisted_model_load(monkeypatch, tmp_path):
    model_path = tmp_path / "xgb_live_model.pkl"
    model_path.write_bytes(b"placeholder")
    events = []

    def _fail_if_called(self, path):
        raise AssertionError(f"load should be skipped for live safe startup: {path}")

    monkeypatch.setattr(tp, "get_active_entry", lambda _kind: None)
    monkeypatch.setattr(tp, "get_shadow_entry", lambda _kind: None)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "LIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD", True, raising=False)
    monkeypatch.setattr(tp.TradePredictor, "load", _fail_if_called, raising=False)
    monkeypatch.setattr(tp, "append_runtime_event", lambda event_type, payload: events.append((event_type, dict(payload))))

    predictor = tp.TradePredictor(model_path=str(model_path), load_existing=True)

    assert predictor.model_runtime == "dummy"
    assert predictor.xgb_available is False
    assert isinstance(predictor.models.get("GLOBAL"), DummyClassifier)
    assert predictor.meta.get("degraded_reason") == "live_startup_skip_persisted_model_load"
    assert events
    assert events[0][0] == "predictor_degraded_startup"
    assert events[0][1]["execution_mode"] == "LIVE"
