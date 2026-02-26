from __future__ import annotations

from config import config as cfg
import core.orchestrator as orchestrator


class _CB:
    def __init__(self, halted: bool, reason: str | None = None):
        self._halted = halted
        self.halt_reason = reason

    def is_halted(self):
        return self._halted


def test_resolve_global_halt_reason_prioritizes_kill_switch(monkeypatch):
    monkeypatch.setattr(cfg, "KILL_SWITCH", True, raising=False)
    monkeypatch.setattr(orchestrator.risk_halt, "is_halted", lambda: True)
    reason = orchestrator.resolve_global_halt_reason(_CB(halted=True, reason="CB_ERROR_STORM"))
    assert reason == "KILL_SWITCH"


def test_resolve_global_halt_reason_returns_risk_halt_when_set(monkeypatch):
    monkeypatch.setattr(cfg, "KILL_SWITCH", False, raising=False)
    monkeypatch.setattr(orchestrator.risk_halt, "is_halted", lambda: True)
    reason = orchestrator.resolve_global_halt_reason(_CB(halted=False))
    assert reason == "RISK_HALT"


def test_resolve_global_halt_reason_uses_circuit_breaker_when_no_other_halts(monkeypatch):
    monkeypatch.setattr(cfg, "KILL_SWITCH", False, raising=False)
    monkeypatch.setattr(orchestrator.risk_halt, "is_halted", lambda: False)
    reason = orchestrator.resolve_global_halt_reason(_CB(halted=True, reason="CB_FEED_UNHEALTHY"))
    assert reason == "CB_FEED_UNHEALTHY"
