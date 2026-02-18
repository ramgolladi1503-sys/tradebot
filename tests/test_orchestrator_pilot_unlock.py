from dataclasses import replace
from datetime import datetime

import core.orchestrator as orchestrator_mod
from config import config as cfg
from core.orchestrator import Orchestrator
from core.time_utils import now_ist
from core.trade_schema import Trade


class _StubBuilder:
    def __init__(self, trade):
        self._trade = trade

    def build_with_trace(self, *args, **kwargs):
        return self._trade, None


def _sample_trade():
    return Trade(
        trade_id="NIFTY-PILOT-1",
        timestamp=datetime.now(),
        symbol="NIFTY",
        instrument="OPT",
        instrument_token=12345,
        strike=25000,
        expiry=now_ist().date().isoformat(),
        side="BUY",
        entry_price=100.0,
        stop_loss=90.0,
        target=125.0,
        qty=2,
        capital_at_risk=300.0,
        expected_slippage=1.0,
        confidence=0.7,
        strategy="TEST",
        regime="NEUTRAL",
    )


def test_pilot_unlock_queues_one_trade_per_day(monkeypatch):
    queued = []
    monkeypatch.setattr(orchestrator_mod, "add_to_queue", lambda trade, queue_path=None, extra=None: queued.append((trade, extra or {})))
    monkeypatch.setattr(orchestrator_mod, "audit_append", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "PAPER_PILOT_UNLOCK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PAPER_PILOT_UNLOCK_CLEAN_CYCLES", 3, raising=False)
    monkeypatch.setattr(cfg, "PAPER_PILOT_UNLOCK_MAX_RISK", 150.0, raising=False)

    orch = Orchestrator.__new__(Orchestrator)
    orch.trade_builder = _StubBuilder(_sample_trade())
    orch._pilot_unlock_clean_cycles = 3
    orch._pilot_unlock_day = now_ist().date().isoformat()
    orch._pilot_unlock_used_day = None

    md = {"symbol": "NIFTY", "indicators_ok": True, "indicators_age_sec": 1.0}
    first = orch._maybe_queue_pilot_unlock(md, gate_reasons=["regime_unstable"], debug_flag=False)
    second = orch._maybe_queue_pilot_unlock(md, gate_reasons=["regime_unstable"], debug_flag=False)

    assert first is not None
    assert len(queued) == 1
    queued_trade, extra = queued[0]
    assert queued_trade.tier == "PILOT"
    assert queued_trade.capital_at_risk <= 150.0
    assert extra["pilot_unlock_reason"] == "PILOT_UNLOCK"
    assert second is None


def test_pilot_unlock_never_applies_in_live(monkeypatch):
    queued = []
    monkeypatch.setattr(orchestrator_mod, "add_to_queue", lambda *args, **kwargs: queued.append((args, kwargs)))
    monkeypatch.setattr(orchestrator_mod, "audit_append", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PAPER_PILOT_UNLOCK_ENABLE", True, raising=False)

    orch = Orchestrator.__new__(Orchestrator)
    orch.trade_builder = _StubBuilder(_sample_trade())
    orch._pilot_unlock_clean_cycles = 10
    orch._pilot_unlock_day = now_ist().date().isoformat()
    orch._pilot_unlock_used_day = None

    md = {"symbol": "NIFTY", "indicators_ok": True, "indicators_age_sec": 1.0}
    out = orch._maybe_queue_pilot_unlock(md, gate_reasons=["regime_unstable"], debug_flag=False)

    assert out is None
    assert queued == []
