from __future__ import annotations

from types import SimpleNamespace

from core.decision_builder import build_decision
from core.execution_engine import ExecutionDecision, evaluate as evaluate_execution
from core.orchestrator import Orchestrator
from core.signal_engine import SignalResult, evaluate as evaluate_signal


def test_signal_engine_and_execution_engine_are_separated() -> None:
    snapshot = {
        "freshness": {"max_tick_age_sec": 0.8, "sla_threshold_sec": 2.0},
        "option_quote": {"ltp": 101.2, "bid": 101.0, "ask": 101.4, "age_ms": 700},
    }
    signal = evaluate_signal(
        snapshot,
        {
            "confidence": 0.82,
            "direction": "BUY",
            "features": {"pattern_flags": ["breakout"], "rank_score": 0.81},
        },
    )
    execution = evaluate_execution(snapshot, signal)

    assert isinstance(signal, SignalResult)
    assert signal.confidence == 0.82
    assert signal.direction == "BUY"
    assert signal.features["rank_score"] == 0.81
    assert isinstance(execution, ExecutionDecision)
    assert execution.can_execute is True
    assert execution.execution_score == 0.82
    assert execution.execution_reject_reason is None


def test_build_decision_merges_signal_v1_and_execution_v1_without_mutating_confidence() -> None:
    signal_result = SignalResult(
        confidence=0.74,
        features={"pattern_flags": ["trend"], "rank_score": 0.73},
        direction="BUY",
    )
    execution_decision = ExecutionDecision(
        can_execute=False,
        execution_score=0.31,
        execution_reject_reason="STALE_SNAPSHOT",
    )

    decision = build_decision(
        meta={"ts_epoch": 1720000000.0, "run_id": "R-1", "symbol": "NIFTY", "timeframe": "1m"},
        market={"spot": 25000.0, "trend_state": "UP", "regime": "TREND", "vol_state": "LOW"},
        signals={"pattern_flags": [], "rank_score": 0.11, "confidence": 0.11},
        strategy={"name": "test_strategy", "direction": "BUY", "entry_reason": "unit_test"},
        risk={"daily_loss_limit": 0.02, "position_limit": 3, "slippage_bps_assumed": 8},
        outcome={"status": "planned", "reject_reasons": []},
        signal_result=signal_result,
        execution_decision=execution_decision,
    )

    # Confidence remains signal-owned, execution-owned score is isolated.
    assert decision.signals.confidence == 0.74
    assert decision.extra["signal_v1"]["confidence"] == 0.74
    assert decision.extra["execution_v1"]["execution_score"] == 0.31
    assert decision.extra["execution_v1"]["execution_reject_reason"] == "STALE_SNAPSHOT"


def test_decision_event_emits_signal_v1_and_execution_v1() -> None:
    orch = Orchestrator.__new__(Orchestrator)
    orch.portfolio = {
        "capital": 100000.0,
        "equity_high": 101000.0,
        "daily_pnl": 1000.0,
        "daily_pnl_pct": 0.01,
        "open_risk": 500.0,
        "open_risk_pct": 0.005,
    }
    orch.loss_streak = {"NIFTY": 0}
    orch.risk_state = SimpleNamespace(daily_max_drawdown=0.01)
    orch._open_risk = lambda: 500.0

    trade = SimpleNamespace(
        trade_id="NIFTY-DECISION-1",
        symbol="NIFTY",
        strategy="TEST",
        regime="TREND",
        side="BUY",
        instrument="OPT",
        instrument_type="OPT",
        expiry="2026-03-11",
        strike=25000,
        option_type="CE",
        right="CE",
        qty_lots=1,
        qty_units=50,
        confidence=0.71,
        global_confidence=0.69,
        pattern_flags=["breakout"],
        trade_score=0.72,
    )
    market_data = {
        "symbol": "NIFTY",
        "market_context": {"execution_mode": "PAPER", "market_open": False},
        "quote_age_sec": 1.0,
    }
    event = orch._build_decision_event(trade, market_data, gatekeeper_allowed=True, veto_reasons=[])

    assert "signal_v1" in event
    assert "execution_v1" in event
    assert event["signal_v1"]["confidence"] == 0.71
    assert event["execution_v1"]["can_execute"] is True
