from core import market_event_graph_live_ohlc_buffer as module


def test_deterministic_test_source_is_explicitly_non_live(monkeypatch):
    monkeypatch.setattr(module.cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    module.reset_live_source_shadow_buffer()
    result = module.record_live_source_shadow_tick(
        symbol="NIFTY", instrument_token=256265, price=100.0,
        source_tick_epoch=1_700_000_000, source_type="deterministic_test",
        feed_identity={"feed_session_id": "fixture-session", "reconnect_generation": 1},
        universe_hash="fixture-universe", packet_kind="FULL", is_full_payload=True,
    )
    assert result["accepted"] is True
    assert result["live_evidence"] is False
    assert result["replay_fixture"] is True
    assert result["fixture_kind"] == "OFFLINE_DETERMINISTIC_TEST"


def test_unknown_source_cannot_activate_test_seam(monkeypatch):
    monkeypatch.setattr(module.cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    result = module.record_live_source_shadow_tick(
        symbol="NIFTY", instrument_token=256265, price=100.0,
        source_tick_epoch=1_700_000_001, source_type="synthetic_live",
        feed_identity={"feed_session_id": "fixture-session", "reconnect_generation": 1},
        universe_hash="fixture-universe",
    )
    assert result == {"accepted": False, "status": "NON_LIVE_SOURCE"}
