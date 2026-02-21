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


def test_update_model_missing_trade_log_does_not_crash(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "TRADE_LOG_PATH", "logs/trade_log.jsonl", raising=False)
    retrain = AutoRetrain(DummyPredictor())
    run_calls = {"count": 0}
    monkeypatch.setattr(
        retrain.research,
        "run",
        lambda **_kwargs: run_calls.__setitem__("count", run_calls["count"] + 1),
    )
    monkeypatch.setattr("core.auto_retrain.compute_decay", lambda *args, **kwargs: {})

    retrain.update_model()

    assert (tmp_path / "logs" / "trade_log.jsonl").exists()
    assert run_calls["count"] == 1
