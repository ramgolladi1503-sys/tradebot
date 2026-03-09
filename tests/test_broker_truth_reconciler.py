from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time

from core.broker_truth_reconciler import BrokerTruthReconciler
from core.events import append_event


@dataclass
class FakeBroker:
    positions_rows: list[dict]
    open_orders_rows: list[dict] = field(default_factory=list)
    recent_fills_rows: list[dict] = field(default_factory=list)
    placed_orders: list[dict] = field(default_factory=list)

    def open_orders(self):
        return list(self.open_orders_rows)

    def positions(self):
        return list(self.positions_rows)

    def recent_fills(self):
        return list(self.recent_fills_rows)

    def place_order(self, payload):
        self.placed_orders.append(dict(payload))
        return {"order_id": f"flat_{len(self.placed_orders)}"}


def _seed_internal_fill(events_file: Path, *, symbol: str, side: str, qty: float, price: float, fill_id: str):
    append_event(
        "fill",
        {
            "order_id": "ord_internal_1",
            "trade_id": "trade_internal_1",
            "fill_id": fill_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
        },
        path=events_file,
    )


def test_broker_truth_reconciler_detects_drift_and_flatten(monkeypatch, tmp_path):
    events_file = tmp_path / "events.jsonl"
    _seed_internal_fill(
        events_file,
        symbol="NIFTY",
        side="BUY",
        qty=1.0,
        price=100.0,
        fill_id="internal_fill_1",
    )
    broker = FakeBroker(
        positions_rows=[{"symbol": "NIFTY", "quantity": 2, "average_price": 101.0}],
        recent_fills_rows=[{"fill_id": "broker_fill_old", "ts": time.time() - 120}],
    )

    emitted_events: list[tuple[str, dict]] = []
    incidents: list[tuple[str, str, dict]] = []
    halts: list[tuple[str, dict]] = []

    monkeypatch.setattr("core.broker_truth_reconciler.events_path", lambda: events_file)
    monkeypatch.setattr(
        "core.broker_truth_reconciler.append_event",
        lambda event_type, payload, **_kwargs: emitted_events.append((event_type, dict(payload))),
    )
    monkeypatch.setattr(
        "core.broker_truth_reconciler.create_incident",
        lambda sev, code, ctx: incidents.append((sev, code, dict(ctx))) or "inc-1",
    )
    monkeypatch.setattr(
        "core.broker_truth_reconciler.risk_halt.set_halt",
        lambda reason, details=None: halts.append((reason, dict(details or {}))),
    )

    reconciler = BrokerTruthReconciler(
        desk_id="DEFAULT",
        broker=broker,
        tolerance_cfg={
            "max_qty": 0.0,
            "max_open_orders": 0,
            "max_price_bps": 10.0,
            "fill_stale_window_sec": 30.0,
            "auto_flatten_on_drift": True,
            "halt_entries_on_detect": True,
        },
        lifecycle=None,
    )
    report = reconciler.run_once()

    assert report["status"] == "DRIFT"
    assert any(item.get("code") == "POSITION_QTY_MISMATCH" for item in report["mismatches"])
    assert incidents and incidents[0][1] == "BROKER_DRIFT"
    assert halts and halts[0][0] == "broker_drift"
    assert broker.placed_orders, "auto flatten must place at least one flatten order"
    assert broker.placed_orders[0]["symbol"] == "NIFTY"
    assert broker.placed_orders[0]["side"] == "SELL"
    assert any(evt[0] == "drift_detected" for evt in emitted_events)
    assert any(evt[0] == "flatten_requested" for evt in emitted_events)
    assert any(action.get("action") == "halt_entries" for action in report["actions"])


def test_broker_truth_reconciler_ok_when_truths_match(monkeypatch, tmp_path):
    events_file = tmp_path / "events.jsonl"
    _seed_internal_fill(
        events_file,
        symbol="BANKNIFTY",
        side="BUY",
        qty=2.0,
        price=200.0,
        fill_id="internal_fill_match",
    )
    broker = FakeBroker(
        positions_rows=[{"symbol": "BANKNIFTY", "quantity": 2, "average_price": 200.0}],
        recent_fills_rows=[{"fill_id": "internal_fill_match", "ts": time.time() - 120}],
    )
    emitted_events: list[tuple[str, dict]] = []
    incidents: list[tuple[str, str, dict]] = []

    monkeypatch.setattr("core.broker_truth_reconciler.events_path", lambda: events_file)
    monkeypatch.setattr(
        "core.broker_truth_reconciler.append_event",
        lambda event_type, payload, **_kwargs: emitted_events.append((event_type, dict(payload))),
    )
    monkeypatch.setattr(
        "core.broker_truth_reconciler.create_incident",
        lambda sev, code, ctx: incidents.append((sev, code, dict(ctx))) or "inc-x",
    )

    reconciler = BrokerTruthReconciler(
        desk_id="DEFAULT",
        broker=broker,
        tolerance_cfg={
            "max_qty": 0.0,
            "max_open_orders": 0,
            "max_price_bps": 25.0,
            "fill_stale_window_sec": 30.0,
            "auto_flatten_on_drift": False,
            "halt_entries_on_detect": False,
        },
        lifecycle=None,
    )
    report = reconciler.run_once()

    assert report["status"] == "OK"
    assert report["mismatches"] == []
    assert incidents == []
    assert not any(evt[0] == "drift_detected" for evt in emitted_events)
