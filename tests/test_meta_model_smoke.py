import json
from pathlib import Path

from core.meta_model import MetaModel


def test_meta_model_suggest_and_log(tmp_path, monkeypatch):
    log_path = tmp_path / "meta.jsonl"
    monkeypatch.setenv("META_SHADOW_LOG_PATH", str(log_path))
    model = MetaModel(log_path=str(log_path))
    md = {"primary_regime": "TREND", "regime_probs": {"TREND": 0.8}}
    stats = {"exec_quality_avg": 60, "decay_probability": 0.2}
    suggestion = model.suggest("TREND_FOLLOW", "xgb", md, stats)
    assert suggestion["suggested_weight"] is not None
    model.log_shadow({"foo": "bar"})
    assert log_path.exists()
    lines = log_path.read_text().splitlines()
    assert lines and json.loads(lines[-1])["foo"] == "bar"
