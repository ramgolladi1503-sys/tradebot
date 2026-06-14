import sqlite3
import threading

import pytest

from config import config as cfg
from core.execution_engine import ExecutionEngine
from core.orders.state_machine import (
    OrderState,
    OrderStateMachine,
    OrderStateTransitionError,
)


def _build_machine(monkeypatch, tmp_path):
    db_path = tmp_path / "trades.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    return OrderStateMachine(db_path=str(db_path))


def test_transition_validation_matrix(monkeypatch, tmp_path):
    _ = _build_machine(monkeypatch, tmp_path)
    assert OrderStateMachine.is_transition_valid(OrderState.NEW, OrderState.SENT)
    assert OrderStateMachine.is_transition_valid(OrderState.SENT, OrderState.ACKNOWLEDGED)
    assert OrderStateMachine.is_transition_valid(OrderState.ACKNOWLEDGED, OrderState.FILLED)
    assert OrderStateMachine.is_transition_valid(OrderState.PARTIAL, OrderState.PARTIAL)

    assert not OrderStateMachine.is_transition_valid(OrderState.NEW, OrderState.FILLED)
    assert not OrderStateMachine.is_transition_valid(OrderState.FILLED, OrderState.CANCELLED)


def test_illegal_transition_raises(monkeypatch, tmp_path):
    sm = _build_machine(monkeypatch, tmp_path)
    sm.create_order(order_id="ORD-1", idempotency_key="idem-1")
    with pytest.raises(OrderStateTransitionError):
        sm.transition(order_id="ORD-1", next_state=OrderState.FILLED, reason="illegal_jump")


def test_transitions_are_persisted_atomically(monkeypatch, tmp_path):
    db_path = tmp_path / "trades.db"
    sm = _build_machine(monkeypatch, tmp_path)
    rec = sm.create_order(order_id="ORD-2", idempotency_key="idem-2")
    assert rec.state == OrderState.NEW

    sm.transition(order_id="ORD-2", next_state=OrderState.SENT, reason="submit")
    sm.transition(order_id="ORD-2", next_state=OrderState.ACKNOWLEDGED, reason="ack")
    sm.transition(order_id="ORD-2", next_state=OrderState.FILLED, reason="fill")
    out = sm.get_order("ORD-2")
    assert out.state == OrderState.FILLED
    assert out.updated_at >= out.created_at

    events = sm.list_events("ORD-2")
    assert [e.to_state for e in events] == [
        OrderState.NEW,
        OrderState.SENT,
        OrderState.ACKNOWLEDGED,
        OrderState.FILLED,
    ]

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT state FROM order_states WHERE order_id=?",
            ("ORD-2",),
        ).fetchone()
        assert row[0] == OrderState.FILLED.value
        count = conn.execute(
            "SELECT COUNT(*) FROM order_state_events WHERE order_id=?",
            ("ORD-2",),
        ).fetchone()[0]
        assert count == 4


def test_transition_updates_are_thread_safe(monkeypatch, tmp_path):
    sm = _build_machine(monkeypatch, tmp_path)
    sm.create_order(order_id="ORD-THREAD", idempotency_key="idem-thread")
    barrier = threading.Barrier(5)
    success = []
    errors = []
    lock = threading.Lock()

    def _worker():
        try:
            barrier.wait(timeout=2.0)
            sm.transition(order_id="ORD-THREAD", next_state=OrderState.SENT, reason="parallel_submit")
            with lock:
                success.append(True)
        except Exception as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3.0)

    assert len(success) == 5
    assert len(errors) == 0
    assert sm.get_order("ORD-THREAD").state == OrderState.SENT
    sent_events = [e for e in sm.list_events("ORD-THREAD") if e.to_state == OrderState.SENT]
    assert len(sent_events) == 1


def test_execution_engine_uses_order_state_machine(monkeypatch, tmp_path):
    _ = _build_machine(monkeypatch, tmp_path)
    engine = ExecutionEngine()
    created = engine.create_order(order_id="ORD-ENG", idempotency_key="idem-eng")
    assert created.state == OrderState.NEW
    engine.transition_order_state(order_id="ORD-ENG", new_state=OrderState.SENT, reason="submitted")
    final = engine.get_order_state("ORD-ENG")
    assert final.state == OrderState.SENT
