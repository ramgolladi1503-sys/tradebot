from core.position_sizer import PositionSizer


def test_low_ml_proba_blocks(monkeypatch):
    monkeypatch.setattr("config.config.ML_MIN_PROBA", 0.6, raising=False)
    monkeypatch.setattr("config.config.ML_FULL_SIZE_PROBA", 0.8, raising=False)
    monkeypatch.setattr("config.config.CONFIDENCE_MIN", 0.6, raising=False)
    monkeypatch.setattr("config.config.CONFIDENCE_FULL", 0.85, raising=False)
    sizer = PositionSizer()
    result = sizer.size_from_budget(
        risk_budget=1000,
        stop_distance_rupees=100,
        ml_proba=0.5,
        confluence_score=0.8,
    )
    assert result.qty == 0
    assert result.reason == "SIZING_BLOCK:LOW_CONFIDENCE"


def test_mid_confidence_scales_qty_down(monkeypatch):
    monkeypatch.setattr("config.config.ML_MIN_PROBA", 0.5, raising=False)
    monkeypatch.setattr("config.config.ML_FULL_SIZE_PROBA", 0.9, raising=False)
    monkeypatch.setattr("config.config.CONFIDENCE_MIN", 0.5, raising=False)
    monkeypatch.setattr("config.config.CONFIDENCE_FULL", 0.9, raising=False)
    sizer = PositionSizer()
    full = sizer.size_from_budget(
        risk_budget=1000,
        stop_distance_rupees=100,
        ml_proba=0.95,
        confluence_score=0.95,
    )
    mid = sizer.size_from_budget(
        risk_budget=1000,
        stop_distance_rupees=100,
        ml_proba=0.7,
        confluence_score=0.7,
    )
    assert full.qty > 0
    assert mid.qty > 0
    assert mid.qty < full.qty
    assert 0.0 < mid.confidence_multiplier < 1.0


def test_high_confidence_keeps_full_size(monkeypatch):
    monkeypatch.setattr("config.config.ML_MIN_PROBA", 0.5, raising=False)
    monkeypatch.setattr("config.config.ML_FULL_SIZE_PROBA", 0.8, raising=False)
    monkeypatch.setattr("config.config.CONFIDENCE_MIN", 0.5, raising=False)
    monkeypatch.setattr("config.config.CONFIDENCE_FULL", 0.8, raising=False)
    sizer = PositionSizer()
    result = sizer.size_from_budget(
        risk_budget=1000,
        stop_distance_rupees=100,
        ml_proba=0.9,
        confluence_score=0.9,
    )
    assert result.qty > 0
    assert result.reason == "OK"
    assert result.confidence_multiplier == 1.0
