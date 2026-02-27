import time

import pandas as pd
import numpy as np

from ml.trade_predictor import TradePredictor


class _StaticModel:
    def __init__(self, prob):
        self._prob = float(prob)
        self.classes_ = [0, 1]

    def predict(self, feats):
        return np.array([1] * len(feats))

    def predict_proba(self, feats):
        return np.array([[1.0 - self._prob, self._prob] for _ in range(len(feats))])


def _build_predictor(prob=0.5):
    p = TradePredictor.__new__(TradePredictor)
    p.model_path = "models/test-online-resilience.pkl"
    p.models = {"GLOBAL": _StaticModel(prob)}
    p.feature_list = ["x"]
    p.meta = {}
    p.shadow_models = {}
    p.shadow_feature_list = None
    p.shadow_meta = {}
    p._xgb_warned = False
    p.xgb_available = False
    p.model_runtime = "dummy"
    p.feature_contract = p._build_feature_contract()
    return p


def test_online_update_failure_does_not_break_predictions(monkeypatch):
    predictor = _build_predictor(prob=0.42)
    monkeypatch.setattr("ml.trade_predictor.cfg.ML_ONLINE_UPDATE_ASYNC", True, raising=False)
    monkeypatch.setattr("ml.trade_predictor.cfg.ML_ONLINE_UPDATE_MAX_BLOCK_SEC", 0.01, raising=False)

    def _boom(self, *_args, **_kwargs):
        raise RuntimeError("train_failed")

    monkeypatch.setattr(TradePredictor, "_train_segmented_payload", _boom, raising=False)

    df = pd.DataFrame([{"x": 1.0, "actual": 1}])
    result = predictor.update_model_online(df, target_col="actual")
    assert result["started"] is True
    # Failure happens in worker thread and must not crash caller.
    conf_now = predictor.predict_confidence(pd.DataFrame([{"x": 1.0}]))
    assert conf_now == 0.42
    assert predictor.wait_for_online_update(timeout_sec=1.0) is True
    conf_after = predictor.predict_confidence(pd.DataFrame([{"x": 1.0}]))
    assert conf_after == 0.42


def test_model_remains_usable_during_async_update_then_swaps(monkeypatch):
    predictor = _build_predictor(prob=0.2)
    monkeypatch.setattr("ml.trade_predictor.cfg.ML_ONLINE_UPDATE_ASYNC", True, raising=False)
    monkeypatch.setattr("ml.trade_predictor.cfg.ML_ONLINE_UPDATE_MAX_BLOCK_SEC", 0.01, raising=False)

    def _slow_payload(self, *_args, **_kwargs):
        time.sleep(0.08)
        return {
            "models": {"GLOBAL": _StaticModel(0.85)},
            "features": ["x"],
            "meta": {"trained_at": "later"},
        }

    monkeypatch.setattr(TradePredictor, "_train_segmented_payload", _slow_payload, raising=False)
    monkeypatch.setattr(TradePredictor, "save", lambda self, path=None: path or self.model_path, raising=False)

    df = pd.DataFrame([{"x": 1.0, "actual": 1}])
    result = predictor.update_model_online(df, target_col="actual")
    assert result["started"] is True
    assert result["completed"] is False

    conf_during = predictor.predict_confidence(pd.DataFrame([{"x": 1.0}]))
    assert conf_during == 0.2

    assert predictor.wait_for_online_update(timeout_sec=1.0) is True
    conf_after = predictor.predict_confidence(pd.DataFrame([{"x": 1.0}]))
    assert conf_after == 0.85
