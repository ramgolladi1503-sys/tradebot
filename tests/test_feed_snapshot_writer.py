import pytest
from core.feed_snapshot_writer import build_feed_snapshot, update_hysteresis

@pytest.fixture(autouse=True)
def reset_hysteresis():
    import core.feed_snapshot_writer as writer
    writer._HYSTERESIS_GOOD_COUNT = 0
    writer._HYSTERESIS_BAD_COUNT = 0
    writer._HYSTERESIS_CURRENT_STATE = False
    yield

def test_build_feed_snapshot():
    raw = {
        "ts_epoch": 1000.0,
        "runtime_state": "BOOTING",
        "ws_connected": True,
    }
    snapshot = build_feed_snapshot(raw_payload=raw, now_epoch=1000.0)
    assert snapshot.ts_epoch == 1000.0
    assert snapshot.runtime_state == "BOOTING"
    assert snapshot.ws_connected is True
    assert snapshot.feed_ok_hysteresis_state.feed_ok is False
    assert snapshot.feed_ok_hysteresis_state.consecutive_good == 0
    assert snapshot.feed_ok_hysteresis_state.consecutive_bad == 0

def test_hysteresis_flip_true():
    raw = {"ts_epoch": 1000.0}
    snapshot = build_feed_snapshot(raw_payload=raw, now_epoch=1000.0)
    
    # 3 good cycles needed to flip true
    snapshot = update_hysteresis(snapshot, raw_feed_ok=True)
    assert snapshot.feed_ok_hysteresis_state.feed_ok is False
    assert snapshot.feed_ok_hysteresis_state.consecutive_good == 1
    
    snapshot = update_hysteresis(snapshot, raw_feed_ok=True)
    assert snapshot.feed_ok_hysteresis_state.feed_ok is False
    assert snapshot.feed_ok_hysteresis_state.consecutive_good == 2
    
    snapshot = update_hysteresis(snapshot, raw_feed_ok=True)
    assert snapshot.feed_ok_hysteresis_state.feed_ok is True
    assert snapshot.feed_ok_hysteresis_state.consecutive_good == 3

def test_hysteresis_flip_false():
    # First flip it to true
    raw = {"ts_epoch": 1000.0}
    snapshot = build_feed_snapshot(raw_payload=raw, now_epoch=1000.0)
    for _ in range(3):
        snapshot = update_hysteresis(snapshot, raw_feed_ok=True)
    assert snapshot.feed_ok_hysteresis_state.feed_ok is True
    assert snapshot.feed_ok_hysteresis_state.consecutive_good == 3

    # Now 3 bad cycles needed to flip false
    snapshot = update_hysteresis(snapshot, raw_feed_ok=False)
    assert snapshot.feed_ok_hysteresis_state.feed_ok is True
    assert snapshot.feed_ok_hysteresis_state.consecutive_bad == 1
    
    snapshot = update_hysteresis(snapshot, raw_feed_ok=False)
    assert snapshot.feed_ok_hysteresis_state.feed_ok is True
    assert snapshot.feed_ok_hysteresis_state.consecutive_bad == 2
    
    snapshot = update_hysteresis(snapshot, raw_feed_ok=False)
    assert snapshot.feed_ok_hysteresis_state.feed_ok is False
    assert snapshot.feed_ok_hysteresis_state.consecutive_bad == 3
