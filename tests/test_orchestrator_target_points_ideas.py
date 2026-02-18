from types import SimpleNamespace

import core.orchestrator as orchestrator_mod
from config import config as cfg
from core.orchestrator import Orchestrator


class _StubBuilder:
    def __init__(self, trade):
        self._trade = trade

    def build_with_trace(self, *args, **kwargs):
        return self._trade, None


def test_target_points_idea_queued_when_threshold_met(monkeypatch):
    queued = []

    def _capture_queue(trade, queue_path=None, extra=None):
        queued.append((trade, queue_path, extra or {}))

    monkeypatch.setattr(orchestrator_mod, "add_to_queue", _capture_queue)
    monkeypatch.setattr(orchestrator_mod, "audit_append", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cfg, "ENABLE_TARGET_POINTS_SUGGESTIONS", True, raising=False)
    monkeypatch.setattr(cfg, "TARGET_POINTS_MIN", 20.0, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "ALLOW_AUX_TRADES_LIVE", False, raising=False)

    trade = SimpleNamespace(
        symbol="NIFTY",
        trade_id="NIFTY-T20-1",
        entry_price=100.0,
        target=122.0,
    )
    orch = Orchestrator.__new__(Orchestrator)
    orch.trade_builder = _StubBuilder(trade)

    out = orch._maybe_queue_target_points_idea({"symbol": "NIFTY"}, debug_flag=False, gate_reasons=["neutral_no_trade"])

    assert out is trade
    assert len(queued) == 1
    _, queue_path, extra = queued[0]
    assert queue_path == orchestrator_mod.TARGET_POINTS_QUEUE_PATH
    assert extra["category"] == "target_points"
    assert extra["tier"] == "OPPORTUNITY"
    assert extra["target_points"] == 22.0


def test_target_points_idea_not_queued_below_threshold(monkeypatch):
    queued = []
    monkeypatch.setattr(orchestrator_mod, "add_to_queue", lambda *args, **kwargs: queued.append((args, kwargs)))
    monkeypatch.setattr(orchestrator_mod, "audit_append", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cfg, "ENABLE_TARGET_POINTS_SUGGESTIONS", True, raising=False)
    monkeypatch.setattr(cfg, "TARGET_POINTS_MIN", 20.0, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)

    trade = SimpleNamespace(
        symbol="NIFTY",
        trade_id="NIFTY-T20-LOW",
        entry_price=100.0,
        target=111.0,
    )
    orch = Orchestrator.__new__(Orchestrator)
    orch.trade_builder = _StubBuilder(trade)

    out = orch._maybe_queue_target_points_idea({"symbol": "NIFTY"}, debug_flag=False, gate_reasons=["neutral_no_trade"])

    assert out is None
    assert queued == []


def test_target_points_idea_skips_quality_blockers(monkeypatch):
    queued = []
    monkeypatch.setattr(orchestrator_mod, "add_to_queue", lambda *args, **kwargs: queued.append((args, kwargs)))
    monkeypatch.setattr(orchestrator_mod, "audit_append", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cfg, "ENABLE_TARGET_POINTS_SUGGESTIONS", True, raising=False)
    monkeypatch.setattr(cfg, "TARGET_POINTS_MIN", 20.0, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)

    trade = SimpleNamespace(
        symbol="NIFTY",
        trade_id="NIFTY-T20-BLOCKED",
        entry_price=100.0,
        target=130.0,
    )
    orch = Orchestrator.__new__(Orchestrator)
    orch.trade_builder = _StubBuilder(trade)

    out = orch._maybe_queue_target_points_idea(
        {"symbol": "NIFTY"},
        debug_flag=False,
        gate_reasons=["indicators_missing_or_stale"],
    )

    assert out is None
    assert queued == []
