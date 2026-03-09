from __future__ import annotations

from config import config as cfg
from core.execution_engine import ExecutionEngine
from core.orders.intent_store import get_intent
from core.orders.order_intent import OrderIntent


def test_client_order_id_rule_is_stable():
    one = OrderIntent.compute_client_order_id(
        trade_id="t-1",
        intent_type="PLACE_ORDER",
        symbol="NIFTY",
        side="BUY",
    )
    two = OrderIntent.compute_client_order_id(
        trade_id="t-1",
        intent_type="PLACE_ORDER",
        symbol="NIFTY",
        side="buy",
    )
    assert one == two


def test_prevent_duplicate_submit_when_intent_already_submitted(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(cfg, "ORDER_INTENT_STORE_PATH", str(tmp_path / "order_intents.sqlite"), raising=False)
    engine = ExecutionEngine()
    submit_calls = {"count": 0}

    def _submit(**_kwargs):
        submit_calls["count"] += 1
        return {"order_id": f"BRK-{submit_calls['count']}", "status": "ACKNOWLEDGED"}

    first = engine.place_order(
        signal_id="trade-dup-1",
        instrument="NIFTY",
        side="BUY",
        timestamp=1_700_000_000,
        submit_order_fn=_submit,
        submit_kwargs={
            "quantity": 1,
            "instrument_token": 256265,
            "order_type": "MARKET",
            "exchange": "NFO",
            "product": "MIS",
            "strategy_id": "TEST",
        },
    )
    assert first["placed"] is True
    assert first.get("idempotent_skip") is False
    client_order_id = str(first.get("client_order_id") or "")
    assert client_order_id
    stored = get_intent(client_order_id)
    assert stored is not None
    assert stored.status == "SUBMITTED"

    # Different timestamp creates a different legacy idempotency key; new client_order_id
    # suppression must still prevent duplicate broker submit.
    second = engine.place_order(
        signal_id="trade-dup-1",
        instrument="NIFTY",
        side="BUY",
        timestamp=1_700_000_001,
        submit_order_fn=_submit,
        submit_kwargs={
            "quantity": 1,
            "instrument_token": 256265,
            "order_type": "MARKET",
            "exchange": "NFO",
            "product": "MIS",
            "strategy_id": "TEST",
        },
    )
    assert second.get("idempotent_skip") is True
    assert second.get("reason") == "intent_already_submitted"
    assert submit_calls["count"] == 1

