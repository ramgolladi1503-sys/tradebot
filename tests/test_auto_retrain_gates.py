import pandas as pd

from config import config as cfg
from core.auto_retrain import AutoRetrain


class DummyPredictor:
    feature_list = []


def test_segments_ok_gate(monkeypatch):
    monkeypatch.setattr(cfg, "ML_SEGMENT_MIN_SAMPLES", 2, raising=False)
    retrain = AutoRetrain(DummyPredictor())
    df = pd.DataFrame({
        "seg_regime": ["TREND", "TREND", "RANGE"],
        "seg_bucket": ["OPEN", "OPEN", "MID"],
        "seg_expiry": [0, 0, 0],
        "seg_vol_q": [1, 1, 1],
    })
    ok, detail = retrain._segments_ok(df)
    assert ok is False
    assert detail.get("reason") == "segment_under_min"


def test_expectancy_below_baseline(monkeypatch):
    monkeypatch.setattr(cfg, "ML_EXPECTANCY_WINDOW", 2, raising=False)
    monkeypatch.setattr(cfg, "ML_EXPECTANCY_MIN_WINDOWS", 2, raising=False)
    retrain = AutoRetrain(DummyPredictor())
    live_df = pd.DataFrame({"pnl": [-1.0, -1.0, -1.0, -1.0]})
    baseline = {"expectancy": 0.5}
    ok, detail = retrain._expectancy_below_baseline(live_df, baseline)
    assert ok is True
    assert detail.get("windows_below") == 2
