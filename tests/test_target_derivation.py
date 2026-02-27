import json

from core.review_queue import add_to_queue
from config import config as cfg


def test_target_derivation_buy(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "TARGET_RR_DEFAULT", 1.5)
    queue_path = tmp_path / "queue.json"
    trade = {
        "trade_id": "TBUY1",
        "symbol": "NIFTY",
        "underlying": "NIFTY",
        "instrument": "OPT",
        "expiry_date": "2026-02-27",
        "strike": 25000,
        "option_type": "CE",
        "tradingsymbol": "NIFTY26FEB25000CE",
        "side": "BUY",
        "entry_price": 100,
        "stop_loss": 90,
    }
    add_to_queue(trade, queue_path=queue_path)
    data = json.loads(queue_path.read_text())
    assert data[0]["target"] == 115.0
    assert data[0]["target_derived"] is True


def test_target_derivation_sell(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "TARGET_RR_DEFAULT", 1.5)
    queue_path = tmp_path / "queue.json"
    trade = {
        "trade_id": "TSELL1",
        "symbol": "NIFTY",
        "underlying": "NIFTY",
        "instrument": "OPT",
        "expiry_date": "2026-02-27",
        "strike": 25000,
        "option_type": "PE",
        "tradingsymbol": "NIFTY26FEB25000PE",
        "side": "SELL",
        "entry_price": 100,
        "stop_loss": 110,
    }
    add_to_queue(trade, queue_path=queue_path)
    data = json.loads(queue_path.read_text())
    assert data[0]["target"] == 85.0
    assert data[0]["target_derived"] is True
