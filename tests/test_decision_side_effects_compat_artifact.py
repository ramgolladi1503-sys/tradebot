from core.decision_side_effects import _indicator_missing_compat_path
from core.live_indicator_readiness import build_live_indicator_readiness_runtime_payload, build_live_indicator_readiness_report


def test_missing_indicator_compatibility_artifact_is_not_authoritative_latest():
    path = _indicator_missing_compat_path()
    assert path.name == "indicator_missing_runtime_latest.json"
    assert path.name != "live_indicator_readiness_latest.json"


def test_authoritative_runtime_payload_preserves_ready_reason():
    report = build_live_indicator_readiness_report([{
        "symbol": "NIFTY", "ohlc_bars_count": 60,
        "indicator_last_update_epoch": 990.0,
        "vwap": 100.0, "rsi": 55.0, "ema": 101.0, "atr": 12.0,
    }], now_epoch=1000.0)
    payload = build_live_indicator_readiness_runtime_payload(report, now_epoch=1000.0)
    row = payload["by_symbol"]["NIFTY"]
    assert row["decision_gate_reason"] == "indicator_ready"
    assert "INDICATORS_MISSING" not in row["blockers"]
