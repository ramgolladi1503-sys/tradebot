from datetime import datetime, timezone

from config import config as cfg
from core.market_event_graph_live_ohlc_buffer import (
    record_live_source_shadow_tick,
    reset_live_source_shadow_buffer,
    shadow_ohlc_buffer,
)


def test_shadow_buffer_disabled_mode_mutates_no_state(monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)

    result = record_live_source_shadow_tick(
        symbol="NIFTY",
        instrument_token=256265,
        price=25000.0,
        source_tick_epoch=100.0,
        source_type="live_websocket",
        feed_identity={"feed_session_id": "session-1", "reconnect_generation": 1},
    )

    assert result["status"] == "DISABLED"
    assert shadow_ohlc_buffer.get_bars("NIFTY") == []


def test_shadow_buffer_accepts_only_new_raw_ticks(monkeypatch):
    reset_live_source_shadow_buffer()
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    identity = {"feed_session_id": "session-1", "reconnect_generation": 7}
    capture = {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "universe_hash": "fba078a4cd7aeb520432b05071a5ac4078e164b809fec0eb80503cb7fe562371",
    }

    first = record_live_source_shadow_tick(
        symbol="NIFTY",
        instrument_token=256265,
        price=25000.0,
        source_tick_epoch=100.0,
        source_type="live_websocket",
        payload_mode="full",
            feed_identity=identity, **capture,
    )
    repeated = record_live_source_shadow_tick(
        symbol="NIFTY",
        instrument_token=256265,
        price=25001.0,
        source_tick_epoch=100.0,
        source_type="live_websocket",
        payload_mode="full",
            feed_identity=identity, **capture,
    )

    assert first["accepted"] is True
    assert repeated["status"] == "STALE_OR_REPEATED_TICK"
    bars = shadow_ohlc_buffer.get_completed_bars("NIFTY", as_of=datetime.fromtimestamp(180.0, tz=timezone.utc))
    assert [bar["close"] for bar in bars] == [25000.0]
    provenance = bars[-1]["bar_provenance"]
    assert provenance["live_feed_session_id"] == "session-1"
    assert provenance["reconnect_generation"] == 7
    assert provenance["instrument_token"] == 256265
