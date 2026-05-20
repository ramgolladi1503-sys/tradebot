from __future__ import annotations

from types import SimpleNamespace

from core.execution_router import ExecutionRouter
from core.orders.state_machine import OrderState


def _trade(**overrides):
    payload = {
        "trade_id": "trade-1",
        "strategy_family": "orb",
        "strategy": "orb",
        "regime": "trend",
        "direction_family": "BUY_CALL",
        "direction": "BUY_CALL",
        "side": "BUY",
        "candidate_type": "EXECUTABLE",
        "signal_score": 0.7,
        "execution_score": 0.8,
        "priority_score": 0.82,
        "final_score": 0.84,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _order(**overrides):
    payload = {
        "order_id": "ord-1",
        "idempotency_key": "idem-1",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_record_paper_execution_outcome_maps_filled_to_executed(monkeypatch):
    captured = []

    def fake_record(payload):
        captured.append(dict(payload))
        return {"written": True, **payload}

    monkeypatch.setattr("core.execution_router.record_paper_outcome", fake_record)
    router = ExecutionRouter()

    result = router._record_paper_execution_outcome(
        trade=_trade(),
        order=_order(),
        terminal_state=OrderState.FILLED,
        reason="fill_confirmed",
        report={
            "fill_status": "FILLED",
            "simulated_pnl": 125.0,
            "slippage_adjusted_pnl": 121.5,
            "realized_r_multiple": 1.2,
        },
        fill_price=101.25,
        slippage=3.5,
    )

    assert result["written"] is True
    payload = captured[0]
    assert captured == [payload]
    assert payload["candidate_id"] == "trade-1"
    assert payload["paper_intent_id"] == "ord-1"
    assert payload["strategy_family"] == "orb"
    assert payload["regime"] == "trend"
    assert payload["direction_family"] == "BUY_CALL"
    assert payload["terminal_status"] == "executed"
    assert payload["simulation_status"] == "FILLED"
    assert payload["final_score"] == 0.84
    assert payload["slippage_cost"] == 3.5
    assert payload["slippage_adjusted_pnl"] == 121.5
    assert payload["metadata"]["entry_order_outcome_only"] is True


def test_record_paper_execution_outcome_maps_abort_states(monkeypatch):
    captured = []
    monkeypatch.setattr("core.execution_router.record_paper_outcome", lambda payload: captured.append(dict(payload)) or payload)
    router = ExecutionRouter()

    router._record_paper_execution_outcome(
        trade=_trade(),
        order=_order(),
        terminal_state=OrderState.REJECTED,
        reason="manual_approval_required",
        report={"reason_if_aborted": "manual_approval_required"},
    )
    router._record_paper_execution_outcome(
        trade=_trade(trade_id="trade-2"),
        order=_order(order_id="ord-2"),
        terminal_state=OrderState.EXPIRED,
        reason="no_quote",
        report={"reason_if_aborted": "no_quote"},
    )
    router._record_paper_execution_outcome(
        trade=_trade(trade_id="trade-3"),
        order=_order(order_id="ord-3"),
        terminal_state=OrderState.CANCELLED,
        reason="spread_too_wide",
        report={"reason_if_aborted": "spread_too_wide"},
    )

    assert [row["terminal_status"] for row in captured] == [
        "rejected-saved-loss",
        "expired-no-move",
        "timed-exit",
    ]
    assert [row["simulation_status"] for row in captured] == ["REJECTED", "EXPIRED", "CANCELLED"]


def test_record_paper_execution_outcome_ignores_non_terminal_state(monkeypatch):
    captured = []
    monkeypatch.setattr("core.execution_router.record_paper_outcome", lambda payload: captured.append(dict(payload)) or payload)
    router = ExecutionRouter()

    result = router._record_paper_execution_outcome(
        trade=_trade(),
        order=_order(),
        terminal_state=OrderState.PARTIAL,
        reason="partial_fill",
    )

    assert result is None
    assert captured == []


def test_record_paper_execution_outcome_does_not_break_runtime_on_journal_error(monkeypatch):
    def broken_record(_payload):
        raise RuntimeError("journal down")

    monkeypatch.setattr("core.execution_router.record_paper_outcome", broken_record)
    router = ExecutionRouter()

    result = router._record_paper_execution_outcome(
        trade=_trade(),
        order=_order(),
        terminal_state=OrderState.FILLED,
        reason="fill_confirmed",
    )

    assert result is None
    assert router._paper_outcome_write_warned is True
