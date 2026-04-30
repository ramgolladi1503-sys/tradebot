import json
from pathlib import Path

import pandas as pd

from core.trade_identity import compute_trade_key
from core import review_queue


def _make_trade(**overrides):
    base = {
        "trade_id": "T-1",
        "symbol": "NIFTY",
        "instrument": "OPT",
        "expiry_date": "2026-03-02",
        "expiry": "2026-03-02",
        "strike": 25500,
        "option_type": "CE",
        "side": "BUY",
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "target": 115.0,
        "strategy": "CORE",
        "timestamp": "2026-02-26T10:00:00",
    }
    base.update(overrides)
    return base


def _read_queue(path: Path):
    if not path.exists():
        return []
    return json.loads(path.read_text())


def test_same_trade_revalidated(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    review_queue.add_to_queue(_make_trade())
    review_queue.add_to_queue(_make_trade(timestamp="2026-02-26T10:01:00"))
    rows = _read_queue(qpath)
    assert len(rows) == 1
    assert rows[0]["trade_status"] == "REVALIDATED"
    assert rows[0]["update_count"] == 1


def test_trade_updated_on_target_change(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    review_queue.add_to_queue(_make_trade())
    review_queue.add_to_queue(_make_trade(target=120.0, timestamp="2026-02-26T10:02:00"))
    rows = _read_queue(qpath)
    assert len(rows) == 1
    assert rows[0]["trade_status"] == "UPDATED"


def test_invalidated_allows_new_row(tmp_path, monkeypatch):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    trade = _make_trade()
    trade_key = compute_trade_key(
        trade["symbol"],
        trade["expiry_date"],
        trade["strike"],
        trade["option_type"],
        trade["side"],
        trade["strategy"],
    )
    existing = {
        "trade_id": "OLD",
        "trade_key": trade_key,
        "trade_status": "INVALIDATED",
        "symbol": trade["symbol"],
        "expiry_date": trade["expiry_date"],
        "strike": trade["strike"],
        "option_type": trade["option_type"],
        "side": trade["side"],
        "strategy": trade["strategy"],
        "timestamp": "2026-02-26T09:55:00",
    }
    qpath.write_text(json.dumps([existing], indent=2))
    review_queue.add_to_queue(trade)
    rows = _read_queue(qpath)
    assert len(rows) == 2
    assert any(row["trade_status"] == "NEW" for row in rows)
    assert any(row["trade_status"] == "INVALIDATED" for row in rows)


def test_ui_unique_trade_key(tmp_path):
    from dashboard.utils import normalize_trade_df
    df = normalize_trade_df(
        pd.DataFrame(
            [
                _make_trade(timestamp="2026-02-26T10:00:00"),
                _make_trade(timestamp="2026-02-26T10:01:00"),
            ]
        )
    )
    assert df["trade_key"].nunique() == len(df)
