import json
import time

from config import config as cfg
from core.execution_engine import ExecutionEngine
from core.kite_client import kite_client
from core.order_reconciliation_daemon import OrderReconciliationDaemon
from core.orders.state_machine import OrderState, OrderStateMachine


class _FakeBroker:
    def __init__(self, *, orders=None, positions=None, fail_orders_once=False):
        self._orders = list(orders or [])
        self._positions = list(positions or [])
        self._fail_orders_once = bool(fail_orders_once)
        self._order_calls = 0

    def orders(self):
        self._order_calls += 1
        if self._fail_orders_once and self._order_calls == 1:
            raise RuntimeError("network_down")
        return list(self._orders)

    def positions(self):
        return {"net": list(self._positions)}


def _machine(monkeypatch, tmp_path):
    db_path = tmp_path / "trades.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    return OrderStateMachine(db_path=str(db_path))


def _read_events(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def test_reconcile_moves_broker_filled_order_to_filled(monkeypatch, tmp_path):
    sm = _machine(monkeypatch, tmp_path)
    sm.create_order(order_id="OID-1", idempotency_key="idem-1", broker_order_id="BRK-1")
    broker = _FakeBroker(
        orders=[
            {
                "order_id": "BRK-1",
                "status": "COMPLETE",
                "quantity": 10,
                "filled_quantity": 10,
                "pending_quantity": 0,
            }
        ],
        positions=[{"quantity": 10}],
    )
    log_path = tmp_path / "reconcile.jsonl"
    daemon = OrderReconciliationDaemon(
        order_state_machine=sm,
        broker_api=broker,
        log_path=log_path,
        network_retries=1,
    )
    result = daemon.run_cycle_once()
    out = sm.get_order("OID-1")
    assert out.state == OrderState.FILLED
    assert out.filled_qty == 10.0
    assert result.corrections >= 1


def test_reconcile_updates_partial_fill_quantity(monkeypatch, tmp_path):
    sm = _machine(monkeypatch, tmp_path)
    sm.create_order(order_id="OID-2", idempotency_key="idem-2", broker_order_id="BRK-2")
    sm.transition(order_id="OID-2", next_state=OrderState.SENT, reason="submit")
    sm.transition(order_id="OID-2", next_state=OrderState.ACKNOWLEDGED, reason="ack")
    sm.transition(order_id="OID-2", next_state=OrderState.PARTIAL, reason="partial", filled_qty=2)
    broker = _FakeBroker(
        orders=[
            {
                "order_id": "BRK-2",
                "status": "OPEN",
                "quantity": 10,
                "filled_quantity": 6,
                "pending_quantity": 4,
            }
        ],
        positions=[{"quantity": 6}],
    )
    daemon = OrderReconciliationDaemon(order_state_machine=sm, broker_api=broker, network_retries=1)
    result = daemon.run_cycle_once()
    out = sm.get_order("OID-2")
    assert out.state == OrderState.PARTIAL
    assert out.filled_qty == 6.0
    assert result.corrections >= 1


def test_reconcile_marks_missing_broker_order_rejected(monkeypatch, tmp_path):
    sm = _machine(monkeypatch, tmp_path)
    sm.create_order(order_id="OID-3", idempotency_key="idem-3", broker_order_id="BRK-3")
    sm.transition(order_id="OID-3", next_state=OrderState.SENT, reason="submit")
    broker = _FakeBroker(orders=[], positions=[])
    daemon = OrderReconciliationDaemon(order_state_machine=sm, broker_api=broker, network_retries=1)
    result = daemon.run_cycle_once()
    out = sm.get_order("OID-3")
    assert out.state == OrderState.REJECTED
    assert result.corrections >= 1


def test_reconcile_marks_unknown_when_positions_open(monkeypatch, tmp_path):
    sm = _machine(monkeypatch, tmp_path)
    sm.create_order(order_id="OID-4", idempotency_key="idem-4", broker_order_id="BRK-4")
    sm.transition(order_id="OID-4", next_state=OrderState.SENT, reason="submit")
    sm.transition(order_id="OID-4", next_state=OrderState.ACKNOWLEDGED, reason="ack")
    log_path = tmp_path / "reconcile_unknown.jsonl"
    broker = _FakeBroker(orders=[], positions=[{"quantity": 1}])
    daemon = OrderReconciliationDaemon(
        order_state_machine=sm,
        broker_api=broker,
        log_path=log_path,
        network_retries=1,
    )
    result = daemon.run_cycle_once()
    out = sm.get_order("OID-4")
    assert out.state == OrderState.ACKNOWLEDGED
    assert result.corrections >= 1
    events = _read_events(log_path)
    assert any(evt.get("event") == "reconcile_mark_unknown" for evt in events)


def test_reconcile_network_failure_is_resilient(monkeypatch, tmp_path):
    sm = _machine(monkeypatch, tmp_path)
    sm.create_order(order_id="OID-5", idempotency_key="idem-5", broker_order_id="BRK-5")
    log_path = tmp_path / "reconcile_retry.jsonl"
    broker = _FakeBroker(
        orders=[
            {
                "order_id": "BRK-5",
                "status": "OPEN",
                "quantity": 10,
                "filled_quantity": 0,
                "pending_quantity": 10,
            }
        ],
        positions=[],
        fail_orders_once=True,
    )
    daemon = OrderReconciliationDaemon(
        order_state_machine=sm,
        broker_api=broker,
        log_path=log_path,
        network_retries=2,
        retry_delay_sec=0.01,
    )
    result = daemon.run_cycle_once()
    assert result.errors == 0
    events = _read_events(log_path)
    assert any(evt.get("event") == "reconcile_network_retry" for evt in events)


def test_daemon_start_stop_graceful_shutdown(monkeypatch, tmp_path):
    sm = _machine(monkeypatch, tmp_path)
    broker = _FakeBroker(orders=[], positions=[])
    daemon = OrderReconciliationDaemon(
        order_state_machine=sm,
        broker_api=broker,
        log_path=tmp_path / "reconcile_daemon.jsonl",
        interval_sec=0.05,
        network_retries=1,
    )
    started = daemon.start()
    assert started is True
    time.sleep(0.15)
    assert daemon.is_running
    clean = daemon.stop(timeout_sec=2.0)
    assert clean is True
    assert daemon.is_running is False


def test_execution_engine_starts_reconciliation_daemon(monkeypatch, tmp_path):
    sm = _machine(monkeypatch, tmp_path)
    engine = ExecutionEngine(order_state_machine=sm)
    broker = _FakeBroker(orders=[], positions=[])
    daemon = engine.start_reconciliation_daemon(broker_api=broker, interval_sec=0.05)
    assert daemon.is_running is True
    clean = engine.stop_reconciliation_daemon(timeout_sec=2.0)
    assert clean is True


def test_reconcile_daemon_skips_broker_resolution_in_sim(monkeypatch, tmp_path):
    sm = _machine(monkeypatch, tmp_path)
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(
        kite_client,
        "ensure",
        lambda: (_ for _ in ()).throw(AssertionError("reconciliation daemon must not initialize Kite in SIM")),
    )
    log_path = tmp_path / "reconcile_sim.jsonl"
    daemon = OrderReconciliationDaemon(
        order_state_machine=sm,
        log_path=log_path,
        network_retries=1,
    )

    result = daemon.run_cycle_once()

    assert result.errors == 1
    events = _read_events(log_path)
    assert any(evt.get("event") == "reconcile_snapshot_failed" for evt in events)
