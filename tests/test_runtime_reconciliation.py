from __future__ import annotations

import json
from pathlib import Path

from config import config as cfg
from core import trade_store
from core.orders.state_machine import OrderState, OrderStateMachine
from core.reconciliation import restore_runtime_state


class _FakeBroker:
    def __init__(self, *, orders=None, positions=None):
        self._orders = list(orders or [])
        self._positions = list(positions or [])
        self.order_calls = 0
        self.position_calls = 0

    def orders(self):
        self.order_calls += 1
        return list(self._orders)

    def positions(self):
        self.position_calls += 1
        return {"net": list(self._positions)}


def _configure_runtime(monkeypatch, tmp_path):
    db_path = tmp_path / "trades.db"
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(logs_path), raising=False)
    monkeypatch.setattr(
        cfg,
        "RUNTIME_RECONCILIATION_LOG_PATH",
        str(logs_path / "runtime_reconciliation.jsonl"),
        raising=False,
    )
    monkeypatch.setattr(cfg, "RUNTIME_RESTORE_POSITION_LIMIT", 2000, raising=False)
    return db_path, logs_path / "runtime_reconciliation.jsonl"


def _insert_open_trade(trade_id: str):
    trade_store.insert_trade(
        {
            "trade_id": trade_id,
            "timestamp": "2026-03-19T10:00:00Z",
            "symbol": "NIFTY",
            "underlying": "NIFTY",
            "instrument": "EQ",
            "instrument_type": "EQ",
            "side": "BUY",
            "entry": 100.0,
            "stop_loss": 95.0,
            "target": 120.0,
            "qty": 10,
            "qty_units": 10,
            "confidence": 0.7,
            "strategy": "TEST",
            "regime": "TRENDING_UP",
        }
    )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def test_restart_with_open_position_restores_lifecycle_state_correctly(monkeypatch, tmp_path):
    db_path, log_path = _configure_runtime(monkeypatch, tmp_path)
    _insert_open_trade("TR-OPEN-1")

    broker = _FakeBroker(orders=[], positions=[{"symbol": "NIFTY", "quantity": 10}])

    result = restore_runtime_state(broker_api=broker, reconcile_order_state=False)

    assert result["status"] == "ok"
    assert result["open_positions"] == 1
    restored = result["position_reconciliation"]["restored_positions"]
    assert len(restored) == 1
    assert restored[0]["trade_id"] == "TR-OPEN-1"
    assert restored[0]["trade_lifecycle_state"] == "active"
    assert restored[0]["trade_lifecycle_reason"] == "broker_open_position_restored"
    assert "broker_open_position_restored" in result["reason_codes"]
    events = _read_jsonl(log_path)
    assert any(evt.get("reason_code") == "broker_open_position_restored" for evt in events)
    assert db_path.exists()


def test_delayed_ack_already_filled_order_does_not_create_duplicate_local_order(monkeypatch, tmp_path):
    db_path, log_path = _configure_runtime(monkeypatch, tmp_path)
    sm = OrderStateMachine(db_path=str(db_path))
    sm.create_order(
        order_id="OID-ACK-1",
        idempotency_key="idem-ack-1",
        instrument="NIFTY",
        side="BUY",
        quantity=10,
        broker_order_id="BRK-ACK-1",
    )
    sm.transition(order_id="OID-ACK-1", next_state=OrderState.SENT, reason="submit")

    broker = _FakeBroker(
        orders=[
            {
                "order_id": "BRK-ACK-1",
                "status": "COMPLETE",
                "quantity": 10,
                "filled_quantity": 10,
                "pending_quantity": 0,
            }
        ],
        positions=[{"symbol": "NIFTY", "quantity": 10}],
    )

    first = restore_runtime_state(
        broker_api=broker,
        order_state_machine=sm,
        restore_position_state=False,
    )
    second = restore_runtime_state(
        broker_api=broker,
        order_state_machine=sm,
        restore_position_state=False,
    )

    order = sm.get_order("OID-ACK-1")
    matching = [row for row in sm.list_orders(include_terminal=True, limit=20) if row.order_id == "OID-ACK-1"]
    assert len(matching) == 1
    assert order.state == OrderState.FILLED
    assert order.filled_qty == 10.0
    assert first["order_reconciliation"]["corrections"] >= 1
    assert second["status"] == "ok"
    assert second["order_reconciliation"] is None
    events = _read_jsonl(log_path)
    assert any(evt.get("event") == "reconcile_state_sync" for evt in events)


def test_partial_fill_reconciliation_updates_state_safely(monkeypatch, tmp_path):
    db_path, log_path = _configure_runtime(monkeypatch, tmp_path)
    _insert_open_trade("TR-PARTIAL-1")
    sm = OrderStateMachine(db_path=str(db_path))
    sm.create_order(
        order_id="OID-PART-1",
        idempotency_key="idem-part-1",
        instrument="NIFTY",
        side="BUY",
        quantity=10,
        broker_order_id="BRK-PART-1",
    )
    sm.transition(order_id="OID-PART-1", next_state=OrderState.SENT, reason="submit")

    broker = _FakeBroker(
        orders=[
            {
                "order_id": "BRK-PART-1",
                "status": "OPEN",
                "quantity": 10,
                "filled_quantity": 4,
                "pending_quantity": 6,
            }
        ],
        positions=[{"symbol": "NIFTY", "quantity": 4}],
    )

    result = restore_runtime_state(broker_api=broker, order_state_machine=sm)

    order = sm.get_order("OID-PART-1")
    restored = result["position_reconciliation"]["restored_positions"]
    assert order.state == OrderState.PARTIAL
    assert order.filled_qty == 4.0
    assert len(restored) == 1
    assert restored[0]["trade_lifecycle_state"] == "partially_filled"
    assert restored[0]["trade_lifecycle_reason"] == "broker_partial_position_restored"
    assert "broker_partial_position_restored" in result["reason_codes"]
    events = _read_jsonl(log_path)
    assert any(evt.get("reason_code") == "broker_partial_position_restored" for evt in events)
