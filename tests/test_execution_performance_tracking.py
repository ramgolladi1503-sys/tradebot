import time

import pytest

from config import config as cfg
from core.execution_engine import ExecutionEngine
from core.orders.state_machine import OrderState


def _build_engine(monkeypatch, tmp_path, **overrides):
    defaults = {
        "TRADE_DB_PATH": str(tmp_path / "trades.db"),
        "EXEC_PERF_WINDOW_TRADES": 100,
        "EXEC_PERF_MIN_FILL_RATE_PCT": 60.0,
        "EXEC_PERF_MAX_REJECTION_RATE_PCT": 10.0,
        "EXEC_PERF_DISABLE_MINUTES": 30.0,
        "EXEC_PERF_LOG_PATH": str(tmp_path / "execution_performance.jsonl"),
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setattr(cfg, key, value, raising=False)
    return ExecutionEngine()


def _create_and_complete(
    engine: ExecutionEngine,
    *,
    order_id: str,
    instrument: str,
    state: OrderState,
    requested_qty: float = 10.0,
    filled_qty: float | None = None,
    slippage: float | None = None,
    time_to_fill_sec: float | None = None,
    ts_base: float = 1000.0,
):
    engine.create_order(
        order_id=order_id,
        idempotency_key=f"idem-{order_id}",
        instrument=instrument,
        side="BUY",
        requested_qty=requested_qty,
    )
    engine.transition_order_state(
        order_id=order_id,
        new_state=OrderState.SENT,
        reason="sent",
        instrument=instrument,
        side="BUY",
        requested_qty=requested_qty,
        now_epoch=ts_base,
    )
    return engine.transition_order_state(
        order_id=order_id,
        new_state=state,
        reason="done",
        filled_qty=filled_qty,
        slippage=slippage,
        time_to_fill_sec=time_to_fill_sec,
        instrument=instrument,
        side="BUY",
        requested_qty=requested_qty,
        now_epoch=ts_base + 1.0,
    )


def test_execution_metrics_use_rolling_100_window(monkeypatch, tmp_path):
    engine = _build_engine(monkeypatch, tmp_path)
    for idx in range(101):
        state = OrderState.REJECTED if idx == 0 else OrderState.FILLED
        _create_and_complete(
            engine,
            order_id=f"OID-R100-{idx}",
            instrument="NIFTY",
            state=state,
            filled_qty=0.0 if state == OrderState.REJECTED else 10.0,
            ts_base=2000.0 + idx,
        )

    metrics = engine.get_execution_performance_metrics("NIFTY")
    assert metrics["sample_size"] == 100
    assert metrics["fill_rate"] == pytest.approx(100.0)
    assert metrics["rejection_rate"] == pytest.approx(0.0)
    assert metrics["disabled"] is False


def test_instrument_is_disabled_and_blocked_before_send(monkeypatch, tmp_path):
    engine = _build_engine(monkeypatch, tmp_path, EXEC_PERF_DISABLE_MINUTES=30.0)
    base_ts = time.time()

    _create_and_complete(
        engine,
        order_id="OID-DISABLE-FILL",
        instrument="BANKNIFTY",
        state=OrderState.FILLED,
        filled_qty=10.0,
        ts_base=base_ts,
    )
    for idx in range(9):
        _create_and_complete(
            engine,
            order_id=f"OID-DISABLE-RJ-{idx}",
            instrument="BANKNIFTY",
            state=OrderState.REJECTED,
            filled_qty=0.0,
            ts_base=base_ts + 10.0 + idx,
        )

    gate = engine.is_instrument_temporarily_disabled("BANKNIFTY")
    assert gate["disabled"] is True
    assert gate["disable_reason"] is not None

    submit_calls = {"n": 0}

    def _submit(**_kwargs):
        submit_calls["n"] += 1
        return {"status": "OPEN", "broker_order_id": "BRK-1"}

    out = engine.place_order(
        signal_id="SIG-BLOCK",
        instrument="BANKNIFTY",
        side="BUY",
        timestamp=1700001111,
        submit_order_fn=_submit,
        submit_kwargs={"qty": 1},
    )
    assert submit_calls["n"] == 0
    assert out["placed"] is False
    assert out["reason"] == "instrument_temporarily_disabled"
    assert out["order"].state == OrderState.REJECTED

    restarted_engine = _build_engine(monkeypatch, tmp_path)
    gate_after_restart = restarted_engine.is_instrument_temporarily_disabled("BANKNIFTY")
    assert gate_after_restart["disabled"] is True


def test_execution_metrics_include_partial_ratio_and_averages(monkeypatch, tmp_path):
    engine = _build_engine(monkeypatch, tmp_path)
    _create_and_complete(
        engine,
        order_id="OID-PARTIAL-1",
        instrument="SENSEX",
        state=OrderState.PARTIAL,
        requested_qty=10.0,
        filled_qty=4.0,
        slippage=1.2,
        time_to_fill_sec=3.0,
        ts_base=4000.0,
    )
    _create_and_complete(
        engine,
        order_id="OID-PARTIAL-2",
        instrument="SENSEX",
        state=OrderState.FILLED,
        requested_qty=10.0,
        filled_qty=10.0,
        slippage=0.8,
        time_to_fill_sec=1.0,
        ts_base=4010.0,
    )

    metrics = engine.get_execution_performance_metrics("SENSEX")
    assert metrics["sample_size"] == 2
    assert metrics["fill_rate"] == pytest.approx(100.0)
    assert metrics["rejection_rate"] == pytest.approx(0.0)
    assert metrics["partial_fill_ratio"] == pytest.approx(0.5)
    assert metrics["avg_slippage"] == pytest.approx(1.0)
    assert metrics["avg_time_to_fill"] == pytest.approx(2.0)
    all_metrics = engine.get_execution_performance_metrics()
    assert "SENSEX" in all_metrics
