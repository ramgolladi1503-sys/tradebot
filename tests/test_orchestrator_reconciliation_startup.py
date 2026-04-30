from types import SimpleNamespace


def test_orchestrator_starts_reconciliation_daemon(monkeypatch):
    import core.orchestrator as orch_mod

    class DummyEE:
        def __init__(self, *args, **kwargs):
            self.start_called = False
            self.reconcile_called = False

        def start_reconciliation_daemon(self, **kwargs):
            self.start_called = True
            self.start_kwargs = kwargs
            return None

        def reconcile_orders_once(self):
            self.reconcile_called = True
            return {"ok": True}

    class Dummy:
        def __init__(self, *args, **kwargs):
            pass

    class DummyStrategyTracker(Dummy):
        def load(self, *args, **kwargs):
            return None

        def load_first_available(self, paths):
            self.load_first_available_paths = list(paths)
            return paths[-1] if paths else None

    class DummyTradeBuilder(Dummy):
        pass

    monkeypatch.setattr(orch_mod, "ExecutionEngine", DummyEE)
    monkeypatch.setattr(orch_mod, "TradePredictor", Dummy)
    monkeypatch.setattr(orch_mod, "ExecutionRouter", Dummy)
    monkeypatch.setattr(orch_mod, "StrategyGatekeeper", Dummy)
    monkeypatch.setattr(orch_mod, "RiskEngine", Dummy)
    monkeypatch.setattr(orch_mod, "ExecutionGuard", Dummy)
    monkeypatch.setattr(orch_mod, "PortfolioRiskAllocator", Dummy)
    monkeypatch.setattr(orch_mod, "StrategyTracker", DummyStrategyTracker)
    monkeypatch.setattr(orch_mod, "TradeBuilder", DummyTradeBuilder)
    monkeypatch.setattr(orch_mod, "AutoRetrain", Dummy)
    monkeypatch.setattr(orch_mod, "StrategyAllocator", Dummy)
    monkeypatch.setattr(orch_mod, "ExposureLedger", Dummy)
    monkeypatch.setattr(orch_mod, "MetaModel", Dummy)
    monkeypatch.setattr(orch_mod, "auto_clear_risk_halt_if_safe", lambda: None)
    monkeypatch.setattr(orch_mod, "ensure_trade_log_exists", lambda: None)
    monkeypatch.setattr(orch_mod, "verify_audit_chain", lambda: (True, "ok", None))
    monkeypatch.setattr(orch_mod.Orchestrator, "_run_preopen_auth_warm_check", lambda self: None)
    monkeypatch.setattr(orch_mod.Orchestrator, "_run_startup_warmup_bootstrap", lambda self: [])
    monkeypatch.setattr(orch_mod.Orchestrator, "_start_depth_ws", lambda self: None)
    monkeypatch.setattr(orch_mod.Orchestrator, "_load_symbol_eps", lambda self: None)
    monkeypatch.setattr(orch_mod.Orchestrator, "_load_suggestion_eval", lambda self: None)
    monkeypatch.setattr(orch_mod, "kite_client", SimpleNamespace(kite=None))
    monkeypatch.setattr(orch_mod.cfg, "ORDER_RECON_DAEMON_ENABLE", True, raising=False)
    monkeypatch.setattr(orch_mod.cfg, "ORDER_RECON_INTERVAL_SEC", 5.0, raising=False)

    orch = orch_mod.Orchestrator(total_capital=1000, poll_interval=1, start_depth_ws_enabled=False)
    ee = orch.execution_engine
    assert ee.start_called is True
    assert ee.reconcile_called is True
    assert orch.strategy_tracker.load_first_available_paths == [
        str(orch_mod.logs_dir() / "strategy_perf.json"),
        str(orch_mod.logs_dir() / "suggestion_strategy_perf.json"),
    ]
