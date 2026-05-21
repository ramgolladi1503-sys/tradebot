from types import SimpleNamespace

import core.recon_once_probe as probe


def test_recon_once_probe_records_success_events(monkeypatch):
    events = []

    def fake_record(event, *, source, details=None, error=None):
        events.append({"event": event, "source": source, "details": details or {}, "error": error or ""})

    monkeypatch.setattr(probe, "_record", fake_record)
    monkeypatch.setattr(probe, "_PATCHED", False)

    class Result:
        scanned_orders = 1
        corrections = 0
        errors = 0
        broker_open_orders = 1
        broker_positions = 1
        started_at = 10.0
        ended_at = 12.5

    class OrderStateMachine:
        def list_orders(self, *, include_terminal=False, limit=100):
            return [{"order_id": "O1"}]

    class OrderReconciliationDaemon:
        def __init__(self):
            self._sm = OrderStateMachine()

        def _resolve_broker_api(self):
            return object()

        def _fetch_broker_orders(self, broker_api):
            return [{"order_id": "B1", "status": "OPEN"}]

        def _fetch_broker_positions(self, broker_api):
            return [{"symbol": "NIFTY", "quantity": 1}]

        def _write_log(self, event, payload, *, level):
            return None

        def run_cycle_once(self):
            broker_api = self._resolve_broker_api()
            self._fetch_broker_orders(broker_api)
            self._fetch_broker_positions(broker_api)
            self._sm.list_orders(include_terminal=False, limit=100)
            self._write_log("summary", {}, level="INFO")
            return Result()

    fake_module = SimpleNamespace(
        OrderReconciliationDaemon=OrderReconciliationDaemon,
        OrderStateMachine=OrderStateMachine,
    )

    probe.install_recon_once_probe(fake_module)
    result = fake_module.OrderReconciliationDaemon().run_cycle_once()

    assert result.scanned_orders == 1
    event_names = [event["event"] for event in events]
    assert "RECON_ONCE_ENTERED" in event_names
    assert "RECON_ONCE_BROKER_RESOLVE_STARTED" in event_names
    assert "RECON_ONCE_BROKER_RESOLVE_COMPLETED" in event_names
    assert "RECON_ONCE_BROKER_ORDERS_FETCH_STARTED" in event_names
    assert "RECON_ONCE_BROKER_ORDERS_FETCH_COMPLETED" in event_names
    assert "RECON_ONCE_BROKER_POSITIONS_FETCH_STARTED" in event_names
    assert "RECON_ONCE_BROKER_POSITIONS_FETCH_COMPLETED" in event_names
    assert "RECON_ONCE_LOCAL_STATE_LOAD_STARTED" in event_names
    assert "RECON_ONCE_LOCAL_STATE_LOAD_COMPLETED" in event_names
    assert "RECON_ONCE_WRITE_STARTED" in event_names
    assert "RECON_ONCE_WRITE_COMPLETED" in event_names
    assert "RECON_ONCE_COMPLETED" in event_names

    completed = [event for event in events if event["event"] == "RECON_ONCE_COMPLETED"][-1]
    assert completed["details"]["scanned_orders"] == 1
    assert completed["details"]["duration_ms"] == 2500.0


def test_recon_once_probe_records_failure_events(monkeypatch):
    events = []

    def fake_record(event, *, source, details=None, error=None):
        events.append({"event": event, "source": source, "details": details or {}, "error": error or ""})

    monkeypatch.setattr(probe, "_record", fake_record)
    monkeypatch.setattr(probe, "_PATCHED", False)

    class OrderStateMachine:
        def list_orders(self, *, include_terminal=False, limit=100):
            return []

    class OrderReconciliationDaemon:
        def _resolve_broker_api(self):
            return object()

        def _fetch_broker_orders(self, broker_api):
            raise RuntimeError("orders fetch boom")

        def run_cycle_once(self):
            broker_api = self._resolve_broker_api()
            self._fetch_broker_orders(broker_api)

    fake_module = SimpleNamespace(
        OrderReconciliationDaemon=OrderReconciliationDaemon,
        OrderStateMachine=OrderStateMachine,
    )

    probe.install_recon_once_probe(fake_module)

    try:
        fake_module.OrderReconciliationDaemon().run_cycle_once()
    except RuntimeError as exc:
        assert "orders fetch boom" in str(exc)
    else:
        raise AssertionError("expected reconciliation failure")

    event_names = [event["event"] for event in events]
    assert "RECON_ONCE_ENTERED" in event_names
    assert "RECON_ONCE_BROKER_RESOLVE_COMPLETED" in event_names
    assert "RECON_ONCE_BROKER_ORDERS_FETCH_STARTED" in event_names
    assert "RECON_ONCE_BROKER_ORDERS_FETCH_FAILED" in event_names
    assert "RECON_ONCE_FAILED" in event_names
