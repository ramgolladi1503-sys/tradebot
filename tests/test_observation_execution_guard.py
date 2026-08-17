from __future__ import annotations

import pytest

from core.broker.mock_broker import MockBroker
from core.execution_adapter import AdvancedExecutionAdapter
from core.execution_engine import ExecutionEngine
from core.observation_execution_guard import ObservationOnlyExecutionBlocked


def _enable_observation(monkeypatch, **extra):
    monkeypatch.setenv("OBSERVATION_ONLY_MODE", "true")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize("method", ["modify_order", "cancel_order"])
def test_observation_mode_blocks_adapter_write_paths(monkeypatch, method):
    _enable_observation(monkeypatch)
    adapter = AdvancedExecutionAdapter()
    with pytest.raises(ObservationOnlyExecutionBlocked):
        getattr(adapter, method)("order")


def test_observation_mode_blocks_live_and_paper_adapter(monkeypatch):
    _enable_observation(monkeypatch, LIVE_TRADING_ENABLED="true", PAPER_TRADING_ENABLED="true")
    adapter = AdvancedExecutionAdapter(live_mode=True)
    with pytest.raises(ObservationOnlyExecutionBlocked):
        adapter.execute_limit_hunt("NIFTY", 1, "BUY", object())


def test_observation_mode_mock_broker_place_order_no_mutation(monkeypatch):
    _enable_observation(monkeypatch)
    broker = MockBroker()
    with pytest.raises(ObservationOnlyExecutionBlocked):
        broker.place_order({"symbol": "NIFTY", "qty": 1, "bid": 1, "ask": 2})
    assert broker._order_seq == 0


def test_observation_mode_blocks_before_intent_and_submit_callback(monkeypatch):
    _enable_observation(
        monkeypatch,
        ALLOW_LIVE_PLACEMENT="true",
        LIVE_TRADING_ENABLED="true",
        PAPER_TRADING_ENABLED="true",
    )
    calls = []
    engine = ExecutionEngine.__new__(ExecutionEngine)
    with pytest.raises(ObservationOnlyExecutionBlocked):
        engine.place_order(
            signal_id="signal",
            instrument="NIFTY",
            side="BUY",
            timestamp=1,
            submit_order_fn=lambda **kwargs: calls.append(kwargs),
            submit_kwargs={"quantity": 1},
        )
    assert calls == []


@pytest.mark.parametrize(
    "flags",
    [
        {},
        {"ALLOW_LIVE_PLACEMENT": "true"},
        {"LIVE_TRADING_ENABLED": "true", "ALLOW_LIVE_PLACEMENT": "true"},
        {"PAPER_TRADING_ENABLED": "true", "AUTO_ORDER": "true"},
    ],
)
def test_observation_guard_dominates_execution_flags(monkeypatch, flags):
    _enable_observation(monkeypatch, **flags)
    broker = MockBroker()
    with pytest.raises(ObservationOnlyExecutionBlocked) as exc:
        broker.place_order({"symbol": "NIFTY", "qty": 1, "bid": 1, "ask": 2})
    assert "OBSERVATION_ONLY_EXECUTION_BLOCKED" in str(exc.value)
