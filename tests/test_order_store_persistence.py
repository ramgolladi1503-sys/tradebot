import sqlite3

from config import config as cfg
from core.execution_engine import ExecutionEngine
from core.orders.state_machine import OrderState, OrderStateMachine


def _build_machine(monkeypatch, tmp_path):
    db_path = tmp_path / "orders_store.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    return OrderStateMachine(db_path=str(db_path)), db_path


def test_orders_table_contains_required_columns_and_data(monkeypatch, tmp_path):
    sm, db_path = _build_machine(monkeypatch, tmp_path)
    rec = sm.create_order(
        order_id="ORD-ST-1",
        idempotency_key="idem-store-1",
        instrument="NIFTY",
        side="BUY",
        quantity=15,
        broker_order_id="BRK-STORE-1",
    )
    assert rec.state == OrderState.NEW
    sm.transition(
        order_id="ORD-ST-1",
        next_state=OrderState.SENT,
        reason="submit",
        avg_fill_price=0.0,
    )

    with sqlite3.connect(str(db_path)) as conn:
        cols = conn.execute("PRAGMA table_info('orders')").fetchall()
        names = {str(row[1]) for row in cols}
        required = {
            "order_id",
            "idempotency_key",
            "instrument",
            "side",
            "quantity",
            "state",
            "filled_qty",
            "avg_fill_price",
            "created_at",
            "updated_at",
        }
        assert required.issubset(names)
        row = conn.execute(
            """
            SELECT order_id, idempotency_key, instrument, side, quantity, state, filled_qty, avg_fill_price
            FROM orders
            WHERE order_id=?
            """,
            ("ORD-ST-1",),
        ).fetchone()
    assert row is not None
    assert row[0] == "ORD-ST-1"
    assert row[1] == "idem-store-1"
    assert row[2] == "NIFTY"
    assert row[3] == "BUY"
    assert float(row[4]) == 15.0
    assert row[5] == OrderState.SENT.value
    assert float(row[6]) == 0.0


def test_execution_engine_startup_loads_open_orders_and_reconciles(monkeypatch, tmp_path):
    sm, _ = _build_machine(monkeypatch, tmp_path)
    sm.create_order(
        order_id="ORD-ST-2",
        idempotency_key="idem-store-2",
        instrument="BANKNIFTY",
        side="SELL",
        quantity=10,
        broker_order_id="BRK-STORE-2",
    )
    sm.transition(order_id="ORD-ST-2", next_state=OrderState.SENT, reason="submit")

    calls = {"count": 0}

    def _fake_reconcile(self):
        calls["count"] += 1
        return {"status": "ok"}

    monkeypatch.setattr(cfg, "ORDER_RECONCILE_ON_STARTUP", True, raising=False)
    monkeypatch.setattr(ExecutionEngine, "reconcile_orders_once", _fake_reconcile)
    engine = ExecutionEngine(order_state_machine=sm)
    open_orders = engine.get_startup_open_orders()

    assert len(open_orders) == 1
    assert open_orders[0].order_id == "ORD-ST-2"
    assert calls["count"] == 1

