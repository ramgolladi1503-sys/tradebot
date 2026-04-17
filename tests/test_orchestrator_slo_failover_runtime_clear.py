from __future__ import annotations

from types import SimpleNamespace

from config import config as cfg
import core.orchestrator as orch_mod


def test_runtime_slo_failover_halt_clears_after_ok_streak(monkeypatch):
    state = SimpleNamespace(_slo_failover_runtime_clear_streak=0)
    clear_calls = {"count": 0}

    monkeypatch.setattr(cfg, "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_OK_STREAK", 2, raising=False)
    monkeypatch.setattr(cfg, "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_MAX_OPEN_POSITIONS", 0, raising=False)
    monkeypatch.setattr(orch_mod, "audit_append", lambda *_a, **_k: None)
    monkeypatch.setattr(
        orch_mod.risk_halt,
        "load_halt",
        lambda: {"halted": True, "reason": "slo_failover"},
    )
    monkeypatch.setattr(orch_mod, "fetch_open_positions_dict", lambda limit=5000: [])
    monkeypatch.setattr(
        orch_mod,
        "evaluate_slo_status",
        lambda enforce_failover=False: {"ok": True, "reasons": [], "status": "OK", "warnings": []},
    )
    monkeypatch.setattr(
        orch_mod.risk_halt,
        "clear_halt",
        lambda: clear_calls.__setitem__("count", clear_calls["count"] + 1),
    )

    orch_mod.Orchestrator._maybe_auto_clear_runtime_slo_failover_halt(state)
    assert clear_calls["count"] == 0
    assert state._slo_failover_runtime_clear_streak == 1

    orch_mod.Orchestrator._maybe_auto_clear_runtime_slo_failover_halt(state)
    assert clear_calls["count"] == 1
    assert state._slo_failover_runtime_clear_streak == 0


def test_runtime_slo_failover_halt_does_not_clear_for_non_slo_reason(monkeypatch):
    state = SimpleNamespace(_slo_failover_runtime_clear_streak=2)
    clear_calls = {"count": 0}

    monkeypatch.setattr(cfg, "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_ENABLE", True, raising=False)
    monkeypatch.setattr(
        orch_mod.risk_halt,
        "load_halt",
        lambda: {"halted": True, "reason": "daily_loss_limit"},
    )
    monkeypatch.setattr(
        orch_mod.risk_halt,
        "clear_halt",
        lambda: clear_calls.__setitem__("count", clear_calls["count"] + 1),
    )

    orch_mod.Orchestrator._maybe_auto_clear_runtime_slo_failover_halt(state)
    assert clear_calls["count"] == 0
    assert state._slo_failover_runtime_clear_streak == 0


def test_runtime_slo_failover_halt_does_not_clear_when_positions_open(monkeypatch):
    state = SimpleNamespace(_slo_failover_runtime_clear_streak=1)
    clear_calls = {"count": 0}

    monkeypatch.setattr(cfg, "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_MAX_OPEN_POSITIONS", 0, raising=False)
    monkeypatch.setattr(
        orch_mod.risk_halt,
        "load_halt",
        lambda: {"halted": True, "reason": "slo_failover"},
    )
    monkeypatch.setattr(
        orch_mod,
        "fetch_open_positions_dict",
        lambda limit=5000: [{"trade_id": "T1"}],
    )
    monkeypatch.setattr(
        orch_mod.risk_halt,
        "clear_halt",
        lambda: clear_calls.__setitem__("count", clear_calls["count"] + 1),
    )

    orch_mod.Orchestrator._maybe_auto_clear_runtime_slo_failover_halt(state)
    assert clear_calls["count"] == 0
    assert state._slo_failover_runtime_clear_streak == 0


def test_runtime_slo_failover_halt_can_clear_with_allowed_auth_latency_breach(monkeypatch):
    state = SimpleNamespace(_slo_failover_runtime_clear_streak=1)
    clear_calls = {"count": 0}

    monkeypatch.setattr(cfg, "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_OK_STREAK", 2, raising=False)
    monkeypatch.setattr(cfg, "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_MAX_OPEN_POSITIONS", 0, raising=False)
    monkeypatch.setattr(
        cfg,
        "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_ALLOWED_REASONS",
        ["AUTH_LATENCY_BREACH"],
        raising=False,
    )
    monkeypatch.setattr(orch_mod, "audit_append", lambda *_a, **_k: None)
    monkeypatch.setattr(
        orch_mod.risk_halt,
        "load_halt",
        lambda: {"halted": True, "reason": "slo_failover"},
    )
    monkeypatch.setattr(orch_mod, "fetch_open_positions_dict", lambda limit=5000: [])
    monkeypatch.setattr(
        orch_mod,
        "evaluate_slo_status",
        lambda enforce_failover=False: {
            "ok": False,
            "status": "BREACH",
            "reasons": ["AUTH_LATENCY_BREACH"],
            "warnings": [],
            "auth": {"ok": True},
        },
    )
    monkeypatch.setattr(
        orch_mod.risk_halt,
        "clear_halt",
        lambda: clear_calls.__setitem__("count", clear_calls["count"] + 1),
    )

    orch_mod.Orchestrator._maybe_auto_clear_runtime_slo_failover_halt(state)
    assert clear_calls["count"] == 1
    assert state._slo_failover_runtime_clear_streak == 0
