from datetime import datetime, timedelta
from types import SimpleNamespace
import json

from config import config as cfg
import core.review_queue as review_queue


def _trade(trade_id: str, ts: datetime, trade_score: float, confidence: float):
    return SimpleNamespace(
        trade_id=trade_id,
        symbol="BANKNIFTY",
        instrument="OPT",
        instrument_id="BANKNIFTY|2026-02-27|60000|CE",
        tradingsymbol="BANKNIFTY26FEB60000CE",
        instrument_token=123456,
        strike=60000,
        expiry="2026-02-27",
        expiry_date="2026-02-27",
        right="CE",
        option_type="CE",
        side="BUY",
        entry_price=200.0,
        stop_loss=180.0,
        target=240.0,
        qty=1,
        confidence=confidence,
        trade_score=trade_score,
        timestamp=ts,
    )


def test_review_queue_dedupe_keeps_best(monkeypatch, tmp_path):
    queue_path = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", queue_path, raising=False)
    monkeypatch.setattr(cfg, "QUEUE_DEDUPE_WINDOW_MIN", 5, raising=False)

    t0 = datetime(2026, 2, 25, 9, 15, 0)
    trade_a = _trade("T1", t0, trade_score=60.0, confidence=0.6)
    trade_b = _trade("T2", t0 + timedelta(minutes=2), trade_score=75.0, confidence=0.5)

    review_queue.add_to_queue(trade_a)
    review_queue.add_to_queue(trade_b)

    data = json.loads(queue_path.read_text())
    assert len(data) == 1
    assert data[0]["trade_id"] == "T2"
    assert float(data[0].get("trade_score")) == 75.0
