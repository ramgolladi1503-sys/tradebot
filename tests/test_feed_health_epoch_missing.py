import json
from pathlib import Path

import core.feed_health as feed_health


def test_feed_health_epoch_missing(tmp_path, monkeypatch):
    sla_path = tmp_path / "sla_check.json"
    payload = {
        "tick_last_epoch": None,
        "depth_last_epoch": None,
        "tick_lag_sec": None,
        "depth_lag_sec": None,
        "tick_msgs_last_min": 0,
        "depth_msgs_last_min": 0,
    }
    sla_path.write_text(json.dumps(payload))
    monkeypatch.setattr(feed_health, "SLA_PATH", sla_path)
    health = feed_health.get_feed_health()
    assert not health["ok"]
    assert "epoch_missing:tick" in health["reasons"]
    assert "epoch_missing:depth" in health["reasons"]
