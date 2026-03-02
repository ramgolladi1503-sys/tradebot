import pandas as pd

from ml.trade_predictor import TradePredictor


def test_update_model_online_persists(monkeypatch):
    predictor = TradePredictor.__new__(TradePredictor)
    predictor.model_path = "models/test-online.pkl"
    predictor.models = {}
    predictor.feature_list = None
    predictor.meta = {}
    calls = {"train_payload": 0, "validate": 0, "save": 0}

    class _Model:
        classes_ = [0, 1]

        def predict(self, feats):
            return [1] * len(feats)

    def _train_payload(self, df, target_col="actual", segment_cols=None, min_samples=None):
        calls["train_payload"] += 1
        assert target_col == "actual"
        assert len(df) == 1
        return {"models": {"GLOBAL": _Model()}, "features": ["ltp"], "meta": {"trained_at": "now"}}

    def _validate(self, payload, df, target_col="actual"):
        calls["validate"] += 1
        assert "models" in payload
        assert len(df) == 1

    def _save(self, path=None):
        calls["save"] += 1
        assert path == predictor.model_path
        return path

    monkeypatch.setattr(TradePredictor, "_train_segmented_payload", _train_payload, raising=False)
    monkeypatch.setattr(TradePredictor, "_validate_payload_predict", _validate, raising=False)
    monkeypatch.setattr(TradePredictor, "save", _save, raising=False)
    monkeypatch.setattr("ml.trade_predictor.cfg.ML_ONLINE_UPDATE_ASYNC", False, raising=False)

    df = pd.DataFrame([{"ltp": 100.0, "actual": 1}])
    res = TradePredictor.update_model_online(predictor, df, target_col="actual")

    assert res["started"] is True
    assert res["completed"] is True
    assert res["success"] is True
    assert calls["train_payload"] == 1
    assert calls["validate"] == 1
    assert calls["save"] == 1
