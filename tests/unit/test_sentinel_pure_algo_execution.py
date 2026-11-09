"""
Unit Tests for Sentinel Automated Execution Router and Dispatcher
==================================================================
Verifies:
1. NIFTY routes to LIVE if enabled, otherwise PAPER.
2. SENSEX and BANKNIFTY are strictly quarantined to PAPER mode even if live is requested.
3. Lot sizes are correctly enforced: NIFTY=65, BANKNIFTY=30, SENSEX=20.
4. Repository safety invariants: read_only, broker_api_called, and is_order_action.
"""

import pytest
from unittest.mock import MagicMock

from core.broker_interface import BrokerOrderResponse
from core.sentinel_execution_router import SentinelExecutionRouter, ExecutionMode
from core.sentinel_automated_order_dispatcher import SentinelAutomatedOrderDispatcher


def test_nifty_execution_routing_defaults_to_paper():
    router = SentinelExecutionRouter(enable_nifty_live=False)
    policy = router.get_policy("NIFTY")
    assert policy.target_mode == ExecutionMode.PAPER
    assert policy.lot_size == 65
    assert policy.allowed_live is False

    intent = {"symbol": "NIFTY 24150 CE", "action": "BUY"}
    routed = router.route_execution_intent("NIFTY", intent)
    assert routed["mode"] == "PAPER"
    assert routed["lot_size"] == 65


def test_sensex_and_banknifty_strictly_isolated_to_paper():
    # Even if enable_nifty_live is True, SENSEX and BANKNIFTY must NEVER be LIVE
    router = SentinelExecutionRouter(enable_nifty_live=True)
    
    # SENSEX check
    sensex_policy = router.get_policy("SENSEX")
    assert sensex_policy.target_mode == ExecutionMode.PAPER
    assert sensex_policy.allowed_live is False
    assert sensex_policy.lot_size == 20
    
    intent_sensex = {"symbol": "SENSEX 78000 CE", "action": "BUY"}
    routed_sensex = router.route_execution_intent("SENSEX", intent_sensex)
    assert routed_sensex["mode"] == "PAPER"
    assert routed_sensex["allowed_for_live"] is False
    assert routed_sensex["lot_size"] == 20

    # BANKNIFTY check
    bn_policy = router.get_policy("BANKNIFTY")
    assert bn_policy.target_mode == ExecutionMode.PAPER
    assert bn_policy.allowed_live is False
    assert bn_policy.lot_size == 30
    
    intent_bn = {"symbol": "BANKNIFTY 51000 CE", "action": "BUY"}
    routed_bn = router.route_execution_intent("BANKNIFTY", intent_bn)
    assert routed_bn["mode"] == "PAPER"
    assert routed_bn["allowed_for_live"] is False
    assert routed_bn["lot_size"] == 30


def test_nifty_live_dispatch_when_explicitly_enabled():
    mock_broker = MagicMock()
    mock_broker.place_order.return_value = BrokerOrderResponse(ok=True, broker_order_id="UPSTOX-ORD-001", status="COMPLETE")

    # Explicitly enabled NIFTY live
    router = SentinelExecutionRouter(enable_nifty_live=True)
    dispatcher = SentinelAutomatedOrderDispatcher(router=router, broker_adapter=mock_broker)

    res = dispatcher.on_apm_entry(
        index_name="NIFTY",
        symbol="NIFTY 24150 CE",
        option_type="CE",
        entry_price=125.0,
        target_pts=30.0,
        sl_pts=15.0,
        setup_reason="RP1_UPPER_AGGRESSIVE_DRIVE",
    )

    assert res.action == "ENTRY_SUBMITTED"
    assert res.mode == "LIVE"
    assert res.qty == 65  # 65 qty lot size
    assert res.order_id == "UPSTOX-ORD-001"
    assert res.is_order_action is True
    assert res.broker_api_called is True
    assert mock_broker.place_order.call_count == 1


def test_sensex_paper_dispatch_even_when_nifty_live_is_active():
    mock_broker = MagicMock()
    events = []

    router = SentinelExecutionRouter(enable_nifty_live=True)
    dispatcher = SentinelAutomatedOrderDispatcher(
        router=router,
        broker_adapter=mock_broker,
        paper_event_writer=lambda name, payload: events.append((name, payload)),
    )

    res = dispatcher.on_apm_entry(
        index_name="SENSEX",
        symbol="SENSEX 78000 CE",
        option_type="CE",
        entry_price=250.0,
        target_pts=50.0,
        sl_pts=30.0,
        setup_reason="TD_PULLBACK_REENTRY_BULL",
    )

    # Must be recorded as PAPER and broker must NOT be called
    assert res.action == "PAPER_RECORDED"
    assert res.mode == "PAPER"
    assert res.qty == 20  # SENSEX lot size
    assert res.read_only is True
    assert res.is_order_action is False
    assert res.broker_api_called is False
    assert mock_broker.place_order.call_count == 0
    assert len(events) == 1
    assert events[0][0] == "paper_order_entry"
    assert events[0][1]["symbol"] == "SENSEX 78000 CE"
