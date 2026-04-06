from types import SimpleNamespace

import main as main_module


class _DummyOrchestrator:
    def __init__(self, *args, **kwargs):
        self.live_monitoring_called = False
        self.execution_router = SimpleNamespace(
            engine=SimpleNamespace(
                start_reconciliation_daemon=lambda **_kwargs: None,
                stop_reconciliation_daemon=lambda **_kwargs: None,
            )
        )

    def live_monitoring(self):
        self.live_monitoring_called = True


def _patch_common_startup(monkeypatch):
    monkeypatch.setattr(main_module, "_ensure_runtime_dirs", lambda repo_root: None)
    monkeypatch.setattr(main_module, "_repair_events_log_if_needed", lambda: None)
    monkeypatch.setattr(main_module, "_check_env", lambda: None)
    monkeypatch.setattr(main_module, "ensure_trade_log_exists", lambda: None)
    monkeypatch.setattr(main_module, "auto_clear_risk_halt_if_safe", lambda: {"cleared": False, "reason_code": "HALT_NOT_ACTIVE"})
    monkeypatch.setattr(main_module, "validate_kite_startup_credentials", lambda **_kwargs: None)


def test_main_audits_db_init_failure(monkeypatch):
    _patch_common_startup(monkeypatch)
    monkeypatch.setattr(main_module.cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(main_module, "ensure_db_ready", lambda: (_ for _ in ()).throw(RuntimeError("db_down")))
    audit_events = []
    runtime_events = []
    monkeypatch.setattr(main_module, "audit_append", lambda payload: audit_events.append(payload))
    monkeypatch.setattr(main_module, "append_runtime_event", lambda event_type, payload: runtime_events.append((event_type, payload)))

    main_module.main()

    assert audit_events[0]["event"] == "STARTUP_DB_INIT_FAIL"
    assert audit_events[0]["stage"] == "db_init"
    assert "db_down" in audit_events[0]["message"]
    assert runtime_events[0][0] == "startup_db_init_fail"


def test_main_audits_security_failure(monkeypatch):
    _patch_common_startup(monkeypatch)
    monkeypatch.setattr(main_module.cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(main_module, "ensure_db_ready", lambda: {"ok": True})
    monkeypatch.setattr(
        main_module,
        "enforce_startup_security",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("token_missing")),
    )
    audit_events = []
    runtime_events = []
    monkeypatch.setattr(main_module, "audit_append", lambda payload: audit_events.append(payload))
    monkeypatch.setattr(main_module, "append_runtime_event", lambda event_type, payload: runtime_events.append((event_type, payload)))

    main_module.main()

    assert audit_events[0]["event"] == "STARTUP_SECURITY_FAIL"
    assert audit_events[0]["stage"] == "startup_security"
    assert "token_missing" in audit_events[0]["message"]
    assert runtime_events[0][0] == "startup_security_fail"


def test_main_audits_can_trade_false_without_blocking_orchestrator(monkeypatch):
    _patch_common_startup(monkeypatch)
    monkeypatch.setattr(main_module.cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(main_module.cfg, "LIVE_PILOT_MODE", True, raising=False)
    monkeypatch.setattr(main_module.cfg, "ORDER_RECON_ENABLED", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "BROKER_TRUTH_RECONCILE_ENABLED", False, raising=False)
    monkeypatch.setattr(main_module, "ensure_db_ready", lambda: {"ok": True})
    monkeypatch.setattr(main_module, "enforce_startup_security", lambda **_kwargs: None)
    monkeypatch.setattr(
        main_module,
        "run_readiness_check",
        lambda write_log=True: {
            "state": "DEGRADED",
            "can_trade": False,
            "ready": False,
            "market_open": True,
            "warnings": ["feed_stale"],
            "blockers": ["feed_stale"],
            "reasons": ["feed_stale"],
        },
    )
    dummy = _DummyOrchestrator()
    monkeypatch.setattr(main_module, "Orchestrator", lambda **_kwargs: dummy)
    audit_events = []
    runtime_events = []
    monkeypatch.setattr(main_module, "audit_append", lambda payload: audit_events.append(payload))
    monkeypatch.setattr(main_module, "append_runtime_event", lambda event_type, payload: runtime_events.append((event_type, payload)))

    main_module.main()

    readiness_events = [evt for evt in audit_events if evt.get("event") == "READINESS_CAN_TRADE_FALSE"]
    assert readiness_events
    assert readiness_events[0]["state"] == "DEGRADED"
    assert readiness_events[0]["warnings"] == ["feed_stale"]
    assert any(event_type == "readiness_can_trade_false" for event_type, _payload in runtime_events)
    assert dummy.live_monitoring_called is True


def test_main_allows_monitoring_startup_when_only_risk_halt_blocks(monkeypatch):
    _patch_common_startup(monkeypatch)
    monkeypatch.setattr(main_module.cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(main_module.cfg, "LIVE_PILOT_MODE", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "ORDER_RECON_ENABLED", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "BROKER_TRUTH_RECONCILE_ENABLED", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "READINESS_ALLOW_RISK_HALT_MONITORING_STARTUP", True, raising=False)
    monkeypatch.setattr(main_module.cfg, "READINESS_GLOBAL_ABORT_BLOCKERS", ["risk_halt_active"], raising=False)
    monkeypatch.setattr(main_module.cfg, "READINESS_GLOBAL_ABORT_PREFIXES", [], raising=False)
    monkeypatch.setattr(main_module, "ensure_db_ready", lambda: {"ok": True})
    monkeypatch.setattr(main_module, "enforce_startup_security", lambda **_kwargs: None)
    monkeypatch.setattr(
        main_module,
        "run_readiness_check",
        lambda write_log=True: {
            "state": "BLOCKED",
            "can_trade": False,
            "ready": False,
            "market_open": True,
            "warnings": [],
            "blockers": ["risk_halt_active"],
            "reasons": ["risk_halt_active"],
        },
    )

    class _DummyLock:
        lock_path = "/tmp/kite_session.lock"

        def acquire(self):
            return True, {"pid": 12345, "host": "unit-test", "lock_path": self.lock_path}

        def release(self):
            return None

    monkeypatch.setattr(main_module, "InstanceLock", lambda repo_root_path: _DummyLock())

    dummy = _DummyOrchestrator()
    monkeypatch.setattr(main_module, "Orchestrator", lambda **_kwargs: dummy)
    audit_events = []
    runtime_events = []
    monkeypatch.setattr(main_module, "audit_append", lambda payload: audit_events.append(payload))
    monkeypatch.setattr(main_module, "append_runtime_event", lambda event_type, payload: runtime_events.append((event_type, payload)))

    main_module.main()

    non_global = [evt for evt in audit_events if evt.get("event") == "READINESS_NON_GLOBAL"]
    can_trade_false = [evt for evt in audit_events if evt.get("event") == "READINESS_CAN_TRADE_FALSE"]
    assert non_global
    assert non_global[0]["reasons"] == ["risk_halt_active"]
    assert can_trade_false
    assert can_trade_false[0]["blockers"] == ["risk_halt_active"]
    assert any(event_type == "readiness_can_trade_false" for event_type, _payload in runtime_events)
    assert dummy.live_monitoring_called is True
