import json
from pathlib import Path

from core import review_queue


def _make_trade(**overrides):
    base = {
        "trade_id": "T-1",
        "symbol": "SENSEX",
        "instrument": "OPT",
        "expiry_date": "2026-03-05",
        "expiry": "2026-03-05",
        "strike": 81700,
        "option_type": "PE",
        "side": "BUY",
        "entry_price": 150.0,
        "stop_loss": 120.0,
        "target": 210.0,
        "strategy": "CORE",
        "timestamp": "2026-02-26T10:00:00",
    }
    base.update(overrides)
    return base


def test_trade_blocked_without_option_subscription(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: False)
    monkeypatch.setattr(review_queue, "get_last_tick", lambda *args, **kwargs: None)
    review_queue.add_to_queue(_make_trade())
    rows = json.loads(qpath.read_text())
    assert rows[0]["entry_status"] in ("NO_LIVE_OPTION_FEED", "NO_TOKEN")
    assert rows[0]["permission"] == "ADVISORY_ONLY"
