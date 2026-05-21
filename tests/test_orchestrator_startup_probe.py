from types import SimpleNamespace

import core.orchestrator_startup_probe as probe


def test_orchestrator_probe_wraps_constructor_stages(monkeypatch):
    events = []

    def fake_record(event, *, source, details=None, error=None):
        events.append({"event": event, "source": source, "details": details or {}, "error": error or ""})

    monkeypatch.setattr(probe, "_record", fake_record)
    monkeypatch.setattr(probe, "_PATCHED", False)

    def auto_clear_risk_halt_if_safe():
        return {"cleared": False}

    def ensure_trade_log_exists():
        return None

    def validate_and_repair_event_log(_path):
        return {"repaired": False}

    def ensure_startup_warmup_bootstrap(symbols):
        return [
            {
                "symbol": symbol,
                "seeded_bars_count": 10,
                "warmup_ok": True,
                "warmup_reason": "unit_test",
            }
            for symbol in list(symbols or [])
        ]

    class RiskState:
        def __init__(self, *args, **kwargs):
            self.ready = True

    class TradePredictor:
        def __init__(self):
            self.ready = True

    class ExecutionEngine:
        def __init__(self):
            self.ready = True

        def start_reconciliation_daemon(self):
            self.recon_daemon_started = True

        def reconcile_orders_once(self):
            self.recon_once_completed = True
            return {"checked": 0}

    class ExecutionRouter:
        def __init__(self):
            self.ready = True

    class StrategyGatekeeper:
        def __init__(self):
            self.ready = True

    class StrategyTracker:
        def __init__(self):
            self.ready = True

    class TradeBuilder:
        def __init__(self, *_args, **_kwargs):
            self.ready = True

    fake_module = SimpleNamespace()

    class Orchestrator:
        def _run_preopen_auth_warm_check(self):
            return {"auth_ok": True}

        def _run_startup_warmup_bootstrap(self):
            return fake_module.ensure_startup_warmup_bootstrap(["NIFTY"])

        def _start_depth_ws_or_raise(self, *, start_depth_ws_enabled=True):
            return None

        def __init__(self):
            # Match real core.orchestrator behavior: these calls resolve through
            # module globals, not closed-over local names. The probe wraps the
            # module attributes, so the test must exercise those attributes.
            fake_module.auto_clear_risk_halt_if_safe()
            fake_module.ensure_trade_log_exists()
            fake_module.validate_and_repair_event_log("events.jsonl")
            self._run_preopen_auth_warm_check()
            self.risk_state = fake_module.RiskState()
            self.predictor = fake_module.TradePredictor()
            self.execution_engine = fake_module.ExecutionEngine()
            self.execution_router = fake_module.ExecutionRouter()
            self.gatekeeper = fake_module.StrategyGatekeeper()
            self.execution_engine.start_reconciliation_daemon()
            self.execution_engine.reconcile_orders_once()
            self.strategy_tracker = fake_module.StrategyTracker()
            self.trade_builder = fake_module.TradeBuilder()
            self._startup_warmup_rows = self._run_startup_warmup_bootstrap()
            self._start_depth_ws_or_raise(start_depth_ws_enabled=False)

        def live_monitoring(self):
            return "DONE"

    fake_module.auto_clear_risk_halt_if_safe = auto_clear_risk_halt_if_safe
    fake_module.ensure_trade_log_exists = ensure_trade_log_exists
    fake_module.validate_and_repair_event_log = validate_and_repair_event_log
    fake_module.ensure_startup_warmup_bootstrap = ensure_startup_warmup_bootstrap
    fake_module.RiskState = RiskState
    fake_module.TradePredictor = TradePredictor
    fake_module.ExecutionEngine = ExecutionEngine
    fake_module.ExecutionRouter = ExecutionRouter
    fake_module.StrategyGatekeeper = StrategyGatekeeper
    fake_module.StrategyTracker = StrategyTracker
    fake_module.TradeBuilder = TradeBuilder
    fake_module.Orchestrator = Orchestrator

    probe._patch_orchestrator_module(fake_module)
    instance = fake_module.Orchestrator()
    assert instance.live_monitoring() == "DONE"
    assert instance._startup_warmup_rows[0]["symbol"] == "NIFTY"

    event_names = [event["event"] for event in events]
    assert "ORCHESTRATOR_INIT_ENTERED" in event_names
    assert "ORCHESTRATOR_SESSION_GUARD_STARTED" in event_names
    assert "ORCHESTRATOR_SESSION_GUARD_COMPLETED" in event_names
    assert "ORCHESTRATOR_TRADE_LOG_READY_COMPLETED" in event_names
    assert "ORCHESTRATOR_EVENT_LOG_REPAIR_COMPLETED" in event_names
    assert "ORCHESTRATOR_AUTH_WARM_CHECK_COMPLETED" in event_names
    assert "ORCHESTRATOR_RISK_STATE_INIT_COMPLETED" in event_names
    assert "ORCHESTRATOR_PREDICTOR_INIT_COMPLETED" in event_names
    assert "ORCHESTRATOR_EXECUTION_ENGINE_INIT_COMPLETED" in event_names
    assert "ORCHESTRATOR_EXECUTION_ROUTER_INIT_COMPLETED" in event_names
    assert "ORCHESTRATOR_GATEKEEPER_INIT_COMPLETED" in event_names
    assert "ORCHESTRATOR_RECON_DAEMON_START_STARTED" in event_names
    assert "ORCHESTRATOR_RECON_DAEMON_START_COMPLETED" in event_names
    assert "ORCHESTRATOR_RECON_ONCE_STARTED" in event_names
    assert "ORCHESTRATOR_RECON_ONCE_COMPLETED" in event_names
    assert "ORCHESTRATOR_STRATEGY_TRACKER_INIT_COMPLETED" in event_names
    assert "ORCHESTRATOR_TRADE_BUILDER_INIT_COMPLETED" in event_names
    assert "ORCHESTRATOR_WARMUP_STARTED" in event_names
    assert "ORCHESTRATOR_WARMUP_MARKET_DATA_STARTED" in event_names
    assert "ORCHESTRATOR_WARMUP_MARKET_DATA_COMPLETED" in event_names
    assert "ORCHESTRATOR_WARMUP_COMPLETED" in event_names
    assert "FEED_START_REQUEST_BOUNDARY_REACHED" in event_names
    assert "ORCHESTRATOR_INIT_COMPLETED" in event_names
    assert "LIVE_MONITORING_CALLING" in event_names
    assert "LIVE_MONITORING_RETURNED" in event_names


def test_orchestrator_probe_records_stage_failure(monkeypatch):
    events = []

    def fake_record(event, *, source, details=None, error=None):
        events.append({"event": event, "source": source, "details": details or {}, "error": error or ""})

    monkeypatch.setattr(probe, "_record", fake_record)
    monkeypatch.setattr(probe, "_PATCHED", False)

    fake_module = SimpleNamespace()

    class TradePredictor:
        def __init__(self):
            raise RuntimeError("predictor boom")

    class Orchestrator:
        def __init__(self):
            self.predictor = fake_module.TradePredictor()

    fake_module.TradePredictor = TradePredictor
    fake_module.Orchestrator = Orchestrator

    probe._patch_orchestrator_module(fake_module)

    try:
        fake_module.Orchestrator()
    except RuntimeError as exc:
        assert "predictor boom" in str(exc)
    else:
        raise AssertionError("expected constructor failure")

    event_names = [event["event"] for event in events]
    assert "ORCHESTRATOR_INIT_ENTERED" in event_names
    assert "ORCHESTRATOR_PREDICTOR_INIT_STARTED" in event_names
    assert "ORCHESTRATOR_PREDICTOR_INIT_FAILED" in event_names
    assert "ORCHESTRATOR_INIT_FAILED" in event_names


def test_orchestrator_probe_records_warmup_market_data_failure(monkeypatch):
    events = []

    def fake_record(event, *, source, details=None, error=None):
        events.append({"event": event, "source": source, "details": details or {}, "error": error or ""})

    monkeypatch.setattr(probe, "_record", fake_record)
    monkeypatch.setattr(probe, "_PATCHED", False)

    fake_module = SimpleNamespace()

    def ensure_startup_warmup_bootstrap(_symbols):
        raise RuntimeError("warmup boom")

    class Orchestrator:
        def _run_startup_warmup_bootstrap(self):
            return fake_module.ensure_startup_warmup_bootstrap(["NIFTY"])

        def __init__(self):
            self._run_startup_warmup_bootstrap()

    fake_module.ensure_startup_warmup_bootstrap = ensure_startup_warmup_bootstrap
    fake_module.Orchestrator = Orchestrator

    probe._patch_orchestrator_module(fake_module)

    try:
        fake_module.Orchestrator()
    except RuntimeError as exc:
        assert "warmup boom" in str(exc)
    else:
        raise AssertionError("expected warmup failure")

    event_names = [event["event"] for event in events]
    assert "ORCHESTRATOR_INIT_ENTERED" in event_names
    assert "ORCHESTRATOR_WARMUP_STARTED" in event_names
    assert "ORCHESTRATOR_WARMUP_MARKET_DATA_STARTED" in event_names
    assert "ORCHESTRATOR_WARMUP_MARKET_DATA_FAILED" in event_names
    assert "ORCHESTRATOR_WARMUP_FAILED" in event_names
    assert "ORCHESTRATOR_INIT_FAILED" in event_names


def test_orchestrator_probe_records_reconciliation_failure(monkeypatch):
    events = []

    def fake_record(event, *, source, details=None, error=None):
        events.append({"event": event, "source": source, "details": details or {}, "error": error or ""})

    monkeypatch.setattr(probe, "_record", fake_record)
    monkeypatch.setattr(probe, "_PATCHED", False)

    fake_module = SimpleNamespace()

    class ExecutionEngine:
        def __init__(self):
            self.ready = True

        def start_reconciliation_daemon(self):
            raise RuntimeError("recon daemon boom")

        def reconcile_orders_once(self):
            return {"checked": 0}

    class Orchestrator:
        def __init__(self):
            self.execution_engine = fake_module.ExecutionEngine()
            self.execution_engine.start_reconciliation_daemon()

    fake_module.ExecutionEngine = ExecutionEngine
    fake_module.Orchestrator = Orchestrator

    probe._patch_orchestrator_module(fake_module)

    try:
        fake_module.Orchestrator()
    except RuntimeError as exc:
        assert "recon daemon boom" in str(exc)
    else:
        raise AssertionError("expected reconciliation failure")

    event_names = [event["event"] for event in events]
    assert "ORCHESTRATOR_INIT_ENTERED" in event_names
    assert "ORCHESTRATOR_EXECUTION_ENGINE_INIT_COMPLETED" in event_names
    assert "ORCHESTRATOR_RECON_DAEMON_START_STARTED" in event_names
    assert "ORCHESTRATOR_RECON_DAEMON_START_FAILED" in event_names
    assert "ORCHESTRATOR_INIT_FAILED" in event_names
