import time
from core.feed_snapshot_reader import normalize_legacy_snapshot

def test_normalize_legacy_snapshot_missing_fields():
    payload = {}
    snapshot = normalize_legacy_snapshot(payload)
    
    assert snapshot.ts_epoch > 0
    # Missing start_epoch is preserved as None
    assert snapshot.start_epoch is None
    assert snapshot.runtime_state == "UNKNOWN"
    assert snapshot.ws_connected is False
    assert snapshot.feed_ok_hysteresis_state.feed_ok is True  # conservative default

def test_normalize_legacy_snapshot_with_data():
    payload = {
        "ts_epoch": 12345.0,
        "start_epoch": 12300.0,
        "runtime_state": "LIVE",
        "ws_connected": True,
        "feed_ok_hysteresis_state": False,
    }
    snapshot = normalize_legacy_snapshot(payload)
    
    assert snapshot.ts_epoch == 12345.0
    assert snapshot.start_epoch == 12300.0
    assert snapshot.runtime_state == "LIVE"
    assert snapshot.ws_connected is True
    assert snapshot.feed_ok_hysteresis_state.feed_ok is False

def test_normalize_legacy_feed_ok_fallback():
    payload = {
        "feed_ok": False
        # feed_ok_hysteresis_state is missing
    }
    snapshot = normalize_legacy_snapshot(payload)
    assert snapshot.feed_ok_hysteresis_state.feed_ok is False
