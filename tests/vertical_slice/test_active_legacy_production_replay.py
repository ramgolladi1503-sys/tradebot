import pytest
import os
import json
from unittest.mock import patch

from config import config as cfg
from core.orchestrator import Orchestrator
from core.replay.legacy_market_data_provider import ReplayMarketDataProvider
from core.recovery_state_machine import RecoveryState
import core.risk_halt
import core.orchestrator

@pytest.fixture
def replay_fixture(tmp_path):
    events = [
        {
            "replay_event_id": "ev1",
            "timestamp": "2024-01-01T09:15:00Z",
            "instrument_token": 256265,
            "tradingsymbol": "NIFTY 50",
            "last_price": 21000.5,
            "volume": 100,
            "source": "FIXTURE_ONLY"
        }
    ]
    file_path = tmp_path / "test_fixture.jsonl"
    with open(file_path, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")
    return str(file_path)

@patch("core.kite_client.KiteClient.submit_order")
def test_legacy_production_pipeline_with_replay(mock_place_order, replay_fixture, monkeypatch):
    cfg.EXECUTION_MODE = "PAPER"
    cfg.PLANNING_NO_SIGNAL_FALLBACK_ENABLE = False
    cfg.REQUIRE_LIVE_QUOTES = True
    
    # Prevent background threads and locks from hanging the test
    monkeypatch.setattr(cfg, "ORCHESTRATOR_FAST_LOOP_ENABLE", False, raising=False)
    monkeypatch.setattr(Orchestrator, "_start_depth_ws", lambda self: None)
    monkeypatch.setattr("core.recovery_state_machine.evaluate_feed_state", lambda _: RecoveryState.HEALTHY, raising=False)
    monkeypatch.setattr("core.orchestrator.evaluate_slo_status", lambda **kwargs: {"status": "OK"}, raising=False)
    monkeypatch.setattr("core.risk_halt.is_halted", lambda: False)
    monkeypatch.setattr("core.risk_halt.set_halt", lambda *a, **k: None)
    monkeypatch.setattr("core.orchestrator.RunLock.acquire", lambda self: (True, "ok"))
    monkeypatch.setattr("core.orchestrator.RunLock.release", lambda self: None)
    
    provider = ReplayMarketDataProvider(replay_fixture)
    orch = Orchestrator()
    
    events = list(provider.read_events())
    provider.publish(events[0])
    
    # Run one legacy monitoring cycle
    orch._legacy_live_monitoring(run_once=True)
    
    # 1. No physical orders placed
    assert mock_place_order.call_count == 0
    
    # 2. Data was parsed and state was read naturally
    from core.tick_store import get_last_tick
    tick = get_last_tick(256265)
    assert tick is not None
    assert tick["ltp"] == 21000.5
