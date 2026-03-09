from __future__ import annotations

from pathlib import Path

from core.regime_monitor import RegimeMonitor


def _build_monitor(tmp_path: Path, **overrides) -> RegimeMonitor:
    params = {
        "window_size": 48,
        "min_samples": 8,
        "collapse_accuracy_min": 0.75,
        "severe_accuracy_min": 0.50,
        "collapse_corr_min": -0.25,
        "severe_windows": 2,
        "status_path": tmp_path / "regime_monitor_status.json",
        "log_path": tmp_path / "regime_monitor.jsonl",
    }
    params.update(overrides)
    return RegimeMonitor(**params)


def test_regime_monitor_detects_collapse_on_consistent_misprediction(tmp_path: Path):
    monitor = _build_monitor(tmp_path)

    # TREND prediction with tiny returns should repeatedly score incorrect.
    price = 100.0
    status = monitor.record_market_snapshot(
        symbol="NIFTY",
        predicted_regime="TREND",
        confidence=0.95,
        ltp=price,
        ts_epoch=1.0,
    )
    assert status["sample_count"] == 0
    for idx in range(1, 12):
        price += 0.005  # 0.005% move << trend threshold, should be incorrect.
        status = monitor.record_market_snapshot(
            symbol="NIFTY",
            predicted_regime="TREND",
            confidence=0.95,
            ltp=price,
            ts_epoch=float(idx + 1),
        )

    assert status["sample_count"] >= 8
    assert status["accuracy"] < 0.5
    assert status["collapsed"] is True
    assert status["severe"] is True


def test_regime_monitor_stays_healthy_when_predictions_match_outcomes(tmp_path: Path):
    monitor = _build_monitor(tmp_path)

    price = 100.0
    monitor.record_market_snapshot(
        symbol="BANKNIFTY",
        predicted_regime="TREND",
        confidence=0.85,
        ltp=price,
        ts_epoch=1.0,
    )
    for idx in range(1, 12):
        price += 1.0  # 1% move >> trend threshold, should score correct.
        status = monitor.record_market_snapshot(
            symbol="BANKNIFTY",
            predicted_regime="TREND",
            confidence=0.85,
            ltp=price,
            ts_epoch=float(idx + 1),
        )

    assert status["sample_count"] >= 8
    assert status["accuracy"] > 0.9
    assert status["collapsed"] is False
    assert status["severe"] is False
