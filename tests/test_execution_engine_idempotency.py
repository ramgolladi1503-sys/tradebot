import sqlite3
import threading

from config import config as cfg
from core.execution_engine import ExecutionEngine
from core.orders.state_machine import OrderState, OrderStateMachine


def test_place_order_generates_stable_sha256_idempotency_key(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    engine = ExecutionEngine()
    one = engine.place_order(
        signal_id="SIG-1",
        instrument="NIFTY",
        side="buy",
        timestamp=1700000000,
    )
    two = engine.place_order(
        signal_id="SIG-1",
        instrument="NIFTY",
        side="BUY",
        timestamp=1700000000,
    )
    assert one["idempotency_key"] == two["idempotency_key"]
    assert one["idempotent_skip"] is False
    assert one["order"].state == OrderState.NEW
    assert two["idempotent_skip"] is True
    assert two["order"].order_id == one["order"].order_id


def test_idempotency_survives_restart(monkeypatch, tmp_path):
    db_path = tmp_path / "trades.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    engine_a = ExecutionEngine()
    first = engine_a.place_order(
        signal_id="SIG-R",
        instrument="BANKNIFTY",
        side="SELL",
        timestamp=1700000001,
    )
    assert first["idempotent_skip"] is False

    engine_b = ExecutionEngine()
    second = engine_b.place_order(
        signal_id="SIG-R",
        instrument="BANKNIFTY",
        side="SELL",
        timestamp=1700000001,
    )
    assert second["idempotent_skip"] is True
    assert second["order"].order_id == first["order"].order_id


def test_place_order_is_concurrency_safe(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    engine = ExecutionEngine()
    barrier = threading.Barrier(6)
    outcomes = []
    lock = threading.Lock()

    def _worker():
        barrier.wait(timeout=2.0)
        out = engine.place_order(
            signal_id="SIG-C",
            instrument="SENSEX",
            side="BUY",
            timestamp=1700000002,
        )
        with lock:
            outcomes.append(out)

    threads = [threading.Thread(target=_worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3.0)

    created = [x for x in outcomes if not x["idempotent_skip"]]
    skipped = [x for x in outcomes if x["idempotent_skip"]]
    assert len(created) == 1
    assert len(skipped) == 5
    order_ids = {x["order"].order_id for x in outcomes}
    assert len(order_ids) == 1


def test_order_state_table_has_idempotency_index(monkeypatch, tmp_path):
    db_path = tmp_path / "trades.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    OrderStateMachine(db_path=str(db_path))
    with sqlite3.connect(str(db_path)) as conn:
        indexes = conn.execute("PRAGMA index_list('order_states')").fetchall()
    names = {str(row[1]) for row in indexes}
    assert "idx_order_states_idempotency_key" in names
