import pytest
import os
import json
from datetime import datetime, timezone

from config import config as cfg
from core.tick_store import get_last_tick
from core.ohlc_buffer import ohlc_buffer
from core.time_utils import now_ist
from core.replay.legacy_market_data_provider import ReplayMarketDataProvider

@pytest.fixture
def replay_source(tmp_path):
    events = [
        {
            "replay_event_id": "ev1",
            "timestamp": "2024-01-01T09:15:00Z",
            "instrument_token": 256265,
            "tradingsymbol": "NIFTY 50",
            "last_price": 21000.5,
            "volume": 100,
            "source": "fixture"
        }
    ]
    file_path = tmp_path / "test_events.jsonl"
    with open(file_path, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")
    return str(file_path)

def test_legacy_production_replay_adapter_updates_state(replay_source):
    provider = ReplayMarketDataProvider(replay_source)
    
    events = list(provider.read_events())
    assert len(events) == 1
    
    event = events[0]
    provider.publish(event)
    
    # 1. State check
    tick = get_last_tick(256265)
    assert tick is not None
    assert tick["ltp"] == 21000.5
    
    # 2. Clock check
    dt = now_ist()
    assert dt.astimezone(timezone.utc).isoformat() == "2024-01-01T09:15:00+00:00"
