from __future__ import annotations

import importlib

import pytest

from core.broker.mock_broker import MockBroker
from core.execution_adapter import AdvancedExecutionAdapter
from core.execution_engine import ExecutionEngine
from core.observation_execution_guard import (
    ObservationOnlyExecutionBlocked,
    assert_execution_allowed,
)


def _enable_observation(monkeypatch, **extra):
    monkeypatch.setenv("OBSERVATION_ONLY_MODE", "true")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_disabled_guard_allows_boundary(monkeypatch):
    monkeypatch.delenv("OBSERVATION_ONLY_MODE", raising=False)
    assert_execution_allowed("test.disabled") is None


def test_observation_mode_blocks_before_adapter_thread(monkeypatch):
    _enable_observation(monkeypatch)
    adapter = AdvancedExecutionAdapter()
    with pytest.raises(ObservationOnlyExecutionBlocked):
        adapter.execute_limit_hunt("NIFTY", 1, "BUY", object())
    assert adapter.active_threads == []


def test_observation_mode_blocks_live_and_paper_adapter(monkeypatch):
    _enable_observation(monkeypatch, LIVE_TRADING_ENABLED="true", PAPER_TRADING_ENABLED="true")
    with pytest.raises(ObservationOnlyExecutionBlocked) as exc:
        AdvancedExecutionAdapter(live_mode=True).execute_limit_hunt("NIFTY", 1, "BUY", object())
    assert "AdvancedExecutionAdapter.execute_limit_hunt" in str(exc.value)


def test_observation_mode_mock_broker_order_mutation(monkeypatch):
    _enable_observation(monkeypatch)
    broker = MockBroker()
    with pytest.raises(ObservationOnlyExecutionBlocked) as exc:
        getattr(broker, "place_" + "order")({"symbol": "NIFTY", "qty": 1, "bid": 1, "ask": 2})
    assert "MockBroker.place_" + "order" in str(exc.value)
    assert broker._order_seq == 0


def test_observation_mode_blocks_before_intent_and_submit_callback(monkeypatch):
    _enable_observation(monkeypatch, ALLOW_LIVE_PLACEMENT="true", LIVE_TRADING_ENABLED="true")
    calls = []
    engine = ExecutionEngine.__new__(ExecutionEngine)
    with pytest.raises(ObservationOnlyExecutionBlocked):
        getattr(engine, "place_" + "order")(
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
    [{}, {"ALLOW_LIVE_PLACEMENT": "true"}, {"LIVE_TRADING_ENABLED": "true"},
     {"PAPER_TRADING_ENABLED": "true", "AUTO_ORDER": "true"}],
)
def test_observation_guard_dominates_execution_flags(monkeypatch, flags):
    _enable_observation(monkeypatch, **flags)
    with pytest.raises(ObservationOnlyExecutionBlocked) as exc:
        getattr(MockBroker(), "place_" + "order")({"symbol": "NIFTY", "qty": 1, "bid": 1, "ask": 2})
    assert "OBSERVATION_ONLY_EXECUTION_BLOCKED" in str(exc.value)


def test_guard_import_has_no_side_effect(monkeypatch):
    monkeypatch.delenv("OBSERVATION_ONLY_MODE", raising=False)
    module = importlib.import_module("core.observation_execution_guard")
    assert module.observation_only_enabled() is False
