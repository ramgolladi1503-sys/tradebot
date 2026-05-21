import time

import core.order_reconciliation_daemon as recon


class _EmptyOrderStateMachine:
    def list_orders(self, *, include_terminal=False, limit=2000):
        return []


class _FakeBroker:
    def __init__(self):
        self.orders_called = 0
        self.positions_called = 0

    def orders(self):
        self.orders_called += 1
        return []

    def positions(self):
        self.positions_called += 1
        return {"net": [], "day": []}


def _set_modes(monkeypatch, *, execution_mode, trading_mode, dry_run=False):
    monkeypatch.setenv("EXECUTION_MODE", execution_mode)
    monkeypatch.setenv("TRADING_MODE", trading_mode)
    if dry_run:
        monkeypatch.setenv("DRY_RUN", "true")
    else:
        monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setattr(recon.cfg, "EXECUTION_MODE", execution_mode, raising=False)
    monkeypatch.setattr(recon.cfg, "TRADING_MODE", trading_mode, raising=False)
    monkeypatch.setattr(recon.cfg, "DRY_RUN", dry_run, raising=False)


def test_paper_mode_reconciliation_skips_global_broker_auth_resolution(monkeypatch, tmp_path):
    _set_modes(monkeypatch, execution_mode="PAPER", trading_mode="PAPER", dry_run=False)

    ensure_calls = []

    def fail_if_called():
        ensure_calls.append("called")
        raise AssertionError("kite_client.ensure must not be called for PAPER reconciliation without injected broker")

    monkeypatch.setattr(recon.kite_client, "ensure", fail_if_called)
    monkeypatch.setattr(recon.kite_client, "kite", _FakeBroker(), raising=False)

    daemon = recon.OrderReconciliationDaemon(
        order_state_machine=_EmptyOrderStateMachine(),
        broker_api=None,
        log_path=tmp_path / "recon.jsonl",
        network_retries=1,
        retry_delay_sec=0,
    )

    started = time.time()
    result = daemon.run_cycle_once()
    elapsed = time.time() - started

    assert ensure_calls == []
    assert result.errors == 1
    assert result.scanned_orders == 0
    assert result.broker_open_orders == 0
    assert result.broker_positions == 0
    assert elapsed < 1.0


def test_paper_mode_reconciliation_uses_injected_broker_without_global_auth(monkeypatch, tmp_path):
    _set_modes(monkeypatch, execution_mode="PAPER", trading_mode="PAPER", dry_run=False)

    ensure_calls = []

    def fail_if_called():
        ensure_calls.append("called")
        raise AssertionError("kite_client.ensure must not be called when broker_api is injected")

    monkeypatch.setattr(recon.kite_client, "ensure", fail_if_called)

    broker = _FakeBroker()
    daemon = recon.OrderReconciliationDaemon(
        order_state_machine=_EmptyOrderStateMachine(),
        broker_api=broker,
        log_path=tmp_path / "recon.jsonl",
        network_retries=1,
        retry_delay_sec=0,
    )

    result = daemon.run_cycle_once()

    assert ensure_calls == []
    assert broker.orders_called == 1
    assert broker.positions_called == 1
    assert result.errors == 0
    assert result.scanned_orders == 0
    assert result.broker_open_orders == 0
    assert result.broker_positions == 0


def test_live_mode_reconciliation_still_attempts_global_broker_auth(monkeypatch, tmp_path):
    _set_modes(monkeypatch, execution_mode="LIVE", trading_mode="LIVE", dry_run=False)

    ensure_calls = []

    def ensure():
        ensure_calls.append("called")

    broker = _FakeBroker()
    monkeypatch.setattr(recon.kite_client, "ensure", ensure)
    monkeypatch.setattr(recon.kite_client, "kite", broker, raising=False)

    daemon = recon.OrderReconciliationDaemon(
        order_state_machine=_EmptyOrderStateMachine(),
        broker_api=None,
        log_path=tmp_path / "recon.jsonl",
        network_retries=1,
        retry_delay_sec=0,
    )

    result = daemon.run_cycle_once()

    assert ensure_calls == ["called"]
    assert broker.orders_called == 1
    assert broker.positions_called == 1
    assert result.errors == 0


def test_dry_run_reconciliation_skips_global_broker_auth_even_with_live_modes(monkeypatch, tmp_path):
    _set_modes(monkeypatch, execution_mode="LIVE", trading_mode="LIVE", dry_run=True)

    ensure_calls = []

    def fail_if_called():
        ensure_calls.append("called")
        raise AssertionError("dry-run reconciliation must not call global broker auth")

    monkeypatch.setattr(recon.kite_client, "ensure", fail_if_called)
    monkeypatch.setattr(recon.kite_client, "kite", _FakeBroker(), raising=False)

    daemon = recon.OrderReconciliationDaemon(
        order_state_machine=_EmptyOrderStateMachine(),
        broker_api=None,
        log_path=tmp_path / "recon.jsonl",
        network_retries=1,
        retry_delay_sec=0,
    )

    result = daemon.run_cycle_once()

    assert ensure_calls == []
    assert result.errors == 1
