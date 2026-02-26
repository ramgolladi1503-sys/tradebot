import pandas as pd

from ml.trade_predictor import TradePredictor


def test_update_model_online_persists(monkeypatch):
    predictor = TradePredictor.__new__(TradePredictor)
    predictor.model_path = "models/test-online.pkl"
    calls = {"train": 0, "save": 0}

    def _train(self, df, target_col="actual"):
        calls["train"] += 1
        assert target_col == "actual"
        assert len(df) == 1

    def _save(self, path=None):
        calls["save"] += 1
        assert path == predictor.model_path
        return path

    monkeypatch.setattr(TradePredictor, "train_new_model", _train, raising=False)
    monkeypatch.setattr(TradePredictor, "save", _save, raising=False)

    df = pd.DataFrame([{"ltp": 100.0, "actual": 1}])
    TradePredictor.update_model_online(predictor, df, target_col="actual")

    assert calls["train"] == 1
    assert calls["save"] == 1
