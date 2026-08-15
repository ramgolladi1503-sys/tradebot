from types import SimpleNamespace

import pytest

import main as main_module


class _DummyOrchestrator:
    def __init__(self, *args, **kwargs):
        self.live_monitoring_called = False
        self.reconciliation_started = False
        self.reconciliation_stopped = False
        self.execution_router = SimpleNamespace(
            engine=SimpleNamespace(
                start_reconciliation_daemon=self._start_reconciliation_daemon,
                stop_reconciliation_daemon=self._stop_reconciliation_daemon,
            )
        )

    def _start_reconciliation_daemon(self, **_kwargs):
        self.reconciliation_started = True

    def _stop_reconciliation_daemon(self, **_kwargs):
        self.reconciliation_stopped = True

    def live_monitoring(self):
        self.live_monitoring_called = True


def _patch_common_startup(monkeypatch):
    monkeypatch.delenv("EXECUTION_MODE", raising=False)
    monkeypatch.delenv("TRADING_MODE", raising=False)
    monkeypatch.delenv("ORDER_RECON_ENABLED", raising=False)
    monkeypatch.setattr(main_module.cfg, "FORCE_FALLBACK_EXECUTION", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "ALLOW_STALE_QUOTES", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "DISABLE_RISK_GATE", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "LIVE_BROKER_ADAPTER_ACTIVE", True, raising=False)
    monkeypatch.setattr(main_module.cfg, "MAX_DAILY_LOSS_PCT", 0.02, raising=False)
    monkeypatch.setattr(main_module.cfg, "DISABLE_KILL_SWITCH", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "ALLOW_SYNTHETIC_OPTION_QUOTES", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "ALLOW_SYNTHETIC_CHAIN", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "ALLOW_MARKET_CLOSED_EXECUTION", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "OFFHOURS_FORCE_ENABLE", False, raising=False)
    monkeypatch.setattr(main_module, "_ensure_runtime_dirs", lambda repo_root: None)
    monkeypatch.setattr(main_module, "_repair_events_log_if_needed", lambda: None)
    monkeypatch.setattr(main_module, "_check_env", lambda: None)
    monkeypatch.setattr(main_module, "ensure_trade_log_exists", lambda: None)
    monkeypatch.setattr(main_module, "auto_clear_risk_halt_if_safe", lambda: {"cleared": False, "reason_code": "HALT_NOT_ACTIVE"})
    monkeypatch.setattr(main_module, "validate_kite_startup_credentials", lambda **_kwargs: None)
    monkeypatch.setattr(main_module, "_initialize_audit_chain", lambda **_kwargs: {"ok": True, "status": "OK", "path": "unit-test"})


def test_runtime_mode_alignment_guard_blocks_mismatch(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "LIVE")
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    monkeypatch.setattr(main_module.cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(main_module.cfg, "TRADING_MODE", "SIM", raising=False)
    audit_events = []
    runtime_events = []
    monkeypatch.setattr(main_module, "audit_append", lambda payload: audit_events.append(payload))
    monkeypatch.setattr(main_module, "append_runtime_event", lambda event_type, payload: runtime_events.append((event_type, payload)))

    with pytest.raises(SystemExit) as exc:
        main_module._validate_runtime_mode_config_alignment("SIM")

    assert exc.value.code == 2
    assert audit_events
    assert audit_events[0]["event"] == "STARTUP_MODE_CONFIG_MISMATCH"
    assert runtime_events
    assert runtime_events[0][0] == "startup_mode_config_mismatch"


def test_runtime_mode_alignment_guard_allows_aligned_live(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "LIVE")
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    monkeypatch.setattr(main_module.cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(main_module.cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(main_module, "audit_append", lambda payload: None)
    monkeypatch.setattr(main_module, "append_runtime_event", lambda event_type, payload: None)

    main_module._validate_runtime_mode_config_alignment("LIVE")


def test_order_reconciliation_defaults_disabled_when_config_key_missing(monkeypatch):
    monkeypatch.delenv("ORDER_RECON_ENABLED", raising=False)
    config = SimpleNamespace()

    assert main_module._order_reconciliation_enabled(config) is False


def test_order_reconciliation_env_override_controls_runtime_flag(monkeypatch):
    config = SimpleNamespace(ORDER_RECON_ENABLED=False)

    monkeypatch.setenv("ORDER_RECON_ENABLED", "true")
    assert main_module._order_reconciliation_enabled(config) is True

    monkeypatch.setenv("ORDER_RECON_ENABLED", "false")
    assert main_module._order_reconciliation_enabled(config) is False


def test_main_does_not_start_order_reconciliation_by_default(monkeypatch):
    _patch_common_startup(monkeypatch)
    monkeypatch.delenv("ORDER_RECON_ENABLED", raising=False)
    monkeypatch.delattr(main_module.cfg, "ORDER_RECON_ENABLED", raising=False)
    monkeypatch.setattr(main_module.cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(main_module.cfg, "BROKER_TRUTH_RECONCILE_ENABLED", False, raising=False)
    monkeypatch.setattr(main_module, "ensure_db_ready", lambda: {"ok": True})
    monkeypatch.setattr(main_module, "enforce_startup_security", lambda **_kwargs: None)
    dummy = _DummyOrchestrator()
    monkeypatch.setattr(main_module, "Orchestrator", lambda **_kwargs: dummy)
    monkeypatch.setattr(main_module, "audit_append", lambda payload: None)
    monkeypatch.setattr(main_module, "append_runtime_event", lambda event_type, payload: None)

    main_module.main()

    assert dummy.live_monitoring_called is True
    assert dummy.reconciliation_started is False
    assert dummy.reconciliation_stopped is True


def test_main_starts_order_reconciliation_only_when_explicitly_enabled(monkeypatch):
    _patch_common_startup(monkeypatch)
    monkeypatch.setenv("ORDER_RECON_ENABLED", "true")
    monkeypatch.setattr(main_module.cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(main_module.cfg, "BROKER_TRUTH_RECONCILE_ENABLED", False, raising=False)
    monkeypatch.setattr(main_module, "ensure_db_ready", lambda: {"ok": True})
    monkeypatch.setattr(main_module, "enforce_startup_security", lambda **_kwargs: None)
    dummy = _DummyOrchestrator()
    monkeypatch.setattr(main_module, "Orchestrator", lambda **_kwargs: dummy)
    monkeypatch.setattr(main_module, "audit_append", lambda payload: None)
    monkeypatch.setattr(main_module, "append_runtime_event", lambda event_type, payload: None)

    main_module.main()

    assert dummy.live_monitoring_called is True
    assert dummy.reconciliation_started is True
    assert dummy.reconciliation_stopped is True


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


def test_startup_feed_breaker_grace_allows_recovery(monkeypatch, capsys):
    _patch_common_startup(monkeypatch)
    monkeypatch.setattr(main_module.cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(main_module.cfg, "LIVE_PILOT_MODE", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "ORDER_RECON_ENABLED", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "BROKER_TRUTH_RECONCILE_ENABLED", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "STARTUP_READINESS_BREAKER_GRACE_ENABLE", True, raising=False)
    monkeypatch.setattr(main_module.cfg, "STARTUP_READINESS_BREAKER_GRACE_SEC", 30.0, raising=False)
    monkeypatch.setattr(main_module.cfg, "STARTUP_READINESS_BREAKER_POLL_SEC", 1.0, raising=False)
    monkeypatch.setattr(main_module.cfg, "READINESS_GLOBAL_ABORT_BLOCKERS", ["feed_circuit_breaker_tripped"], raising=False)
    monkeypatch.setattr(main_module.cfg, "READINESS_GLOBAL_ABORT_PREFIXES", [], raising=False)
    monkeypatch.setattr(main_module, "ensure_db_ready", lambda: {"ok": True})
    monkeypatch.setattr(main_module, "enforce_startup_security", lambda **_kwargs: None)

    readiness_calls = {"count": 0}

    def _readiness_sequence(write_log=True):
        readiness_calls["count"] += 1
        if readiness_calls["count"] == 1:
            return {
                "state": "BLOCKED",
                "can_trade": False,
                "ready": False,
                "market_open": True,
                "warnings": [],
                "blockers": ["feed_circuit_breaker_tripped"],
                "reasons": ["feed_circuit_breaker_tripped"],
                "checks": {"feed_breaker": {"tripped": True, "reason": "slo_failover"}},
            }
        return {
            "state": "READY",
            "can_trade": True,
            "ready": True,
            "market_open": True,
            "warnings": [],
            "blockers": [],
            "reasons": [],
            "checks": {"feed_breaker": {"tripped": False, "reason": None}},
        }

    monkeypatch.setattr(main_module, "run_readiness_check", _readiness_sequence)
    monkeypatch.setattr(
        main_module,
        "get_feed_debug",
        lambda: {
            "ws_connected": True,
            "last_ws_tick_epoch": 12345.0,
            "last_ws_tick_age_sec": 0.5,
            "last_tick_age_sec": 0.5,
        },
    )

    now = {"t": 1000.0}
    monkeypatch.setattr(main_module.time, "time", lambda: now["t"])
    monkeypatch.setattr(main_module.time, "sleep", lambda sec: now.__setitem__("t", now["t"] + float(sec)))

    halt_calls = []
    monkeypatch.setattr(main_module.risk_halt, "set_halt", lambda reason, details: halt_calls.append((reason, details)))

    class _DummyLock:
        lock_path = "/tmp/kite_session.lock"

        def acquire(self):
            return True, {"pid": 12345, "host": "unit-test", "lock_path": self.lock_path}

        def release(self):
            return None

    monkeypatch.setattr(main_module, "InstanceLock", lambda repo_root_path: _DummyLock())

    dummy = _DummyOrchestrator()
    monkeypatch.setattr(main_module, "Orchestrator", lambda **_kwargs: dummy)

    main_module.main()
    out = capsys.readouterr().out

    assert readiness_calls["count"] >= 2
    assert dummy.live_monitoring_called is True
    assert halt_calls == []
    assert "ACTIVE_STARTUP_GRACE_PATH" in out
    assert "STARTUP_WAIT" in out


def test_startup_feed_breaker_grace_times_out_and_aborts(monkeypatch, capsys):
    _patch_common_startup(monkeypatch)
    monkeypatch.setattr(main_module.cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(main_module.cfg, "LIVE_PILOT_MODE", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "ORDER_RECON_ENABLED", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "BROKER_TRUTH_RECONCILE_ENABLED", False, raising=False)
    monkeypatch.setattr(main_module.cfg, "STARTUP_READINESS_BREAKER_GRACE_ENABLE", True, raising=False)
    monkeypatch.setattr(main_module.cfg, "STARTUP_READINESS_BREAKER_GRACE_SEC", 2.0, raising=False)
    monkeypatch.setattr(main_module.cfg, "STARTUP_READINESS_BREAKER_POLL_SEC", 1.0, raising=False)
    monkeypatch.setattr(main_module.cfg, "READINESS_GLOBAL_ABORT_BLOCKERS", ["feed_circuit_breaker_tripped"], raising=False)
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
            "blockers": ["feed_circuit_breaker_tripped"],
            "reasons": ["feed_circuit_breaker_tripped"],
            "checks": {"feed_breaker": {"tripped": True, "reason": "slo_failover"}},
        },
    )
    monkeypatch.setattr(
        main_module,
        "get_feed_debug",
        lambda: {
            "ws_connected": False,
            "last_ws_tick_epoch": 0.0,
            "last_ws_tick_age_sec": 999.0,
            "last_tick_age_sec": 999.0,
        },
    )

    now = {"t": 1000.0}
    monkeypatch.setattr(main_module.time, "time", lambda: now["t"])
    monkeypatch.setattr(main_module.time, "sleep", lambda sec: now.__setitem__("t", now["t"] + float(sec)))

    halt_calls = []
    monkeypatch.setattr(main_module.risk_halt, "set_halt", lambda reason, details: halt_calls.append((reason, details)))

    orchestrator_called = {"value": False}

    def _orchestrator_should_not_run(**_kwargs):
        orchestrator_called["value"] = True
        return _DummyOrchestrator()

    class _DummyLock:
        lock_path = "/tmp/kite_session.lock"

        def acquire(self):
            return True, {"pid": 12345, "host": "unit-test", "lock_path": self.lock_path}

        def release(self):
            return None

    monkeypatch.setattr(main_module, "InstanceLock", lambda repo_root_path: _DummyLock())
    monkeypatch.setattr(main_module, "Orchestrator", _orchestrator_should_not_run)

    main_module.main()
    out = capsys.readouterr().out

    assert halt_calls
    assert halt_calls[0][0] == "readiness_gate_fail"
    assert "feed_circuit_breaker_tripped" in list(halt_calls[0][1].get("reasons") or [])
    assert orchestrator_called["value"] is False
    assert "ACTIVE_STARTUP_GRACE_PATH" in out
