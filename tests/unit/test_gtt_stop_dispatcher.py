"""Unit Tests for GTT Stop Dispatcher
===================================
Verifies co-dispatching broker-side stop loss upon entry, cancellation on target exit,
and fallback local kill-switch activation on broker errors.

Safety Invariants:
read_only = True
is_order_action = False
broker_api_called = False
allowed_for_live_execution = False
"""

import pytest
from core.orders.gtt_stop_dispatcher import (
    GTTStopDispatcher,
    GTTOrderRequest,
    GTTOrderResponse,
    StopOrderType,
)


class MockGTTBroker:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.placed_orders = []
        self.cancelled_orders = []

    def place_gtt_order(self, request: GTTOrderRequest) -> GTTOrderResponse:
        if self.should_fail:
            raise RuntimeError("Upstox GTT API timeout / 503")
        order_id = f"GTT_{len(self.placed_orders) + 1}"
        self.placed_orders.append((order_id, request))
        return GTTOrderResponse(
            success=True,
            gtt_order_id=order_id,
            status="ACTIVE",
            message="Broker GTT placed",
            read_only=False,
            is_order_action=True,
            broker_api_called=True,
        )

    def cancel_gtt_order(self, gtt_order_id: str) -> bool:
        if self.should_fail:
            raise RuntimeError("Cancel failed")
        self.cancelled_orders.append(gtt_order_id)
        return True


def test_safety_invariants_simulated():
    dispatcher = GTTStopDispatcher(broker_adapter=None, enable_live_dispatch=False)
    resp = dispatcher.dispatch_stop_on_entry_fill(
        index_name="NIFTY",
        symbol="NIFTY 25450 CE",
        instrument_token="NSE_FO|45409",
        entry_price=20.0,
        sl_pts=3.0,
        qty=75,
    )
    assert resp.read_only is True
    assert resp.is_order_action is False
    assert resp.broker_api_called is False
    assert resp.allowed_for_live_execution is False
    assert resp.success is True
    assert resp.status == "ACTIVE"


def test_stop_trigger_calculation():
    dispatcher = GTTStopDispatcher()
    # Buy entry at 20.0, stop loss 3.12 pts -> 16.88 -> tick rounded to 16.90
    trigger = dispatcher.calculate_stop_trigger(entry_price=20.0, sl_pts=3.12, side="BUY")
    assert trigger == 16.90

    # Sell entry at 20.0, stop loss 3.12 pts -> 23.12 -> tick rounded to 23.10
    trigger_sell = dispatcher.calculate_stop_trigger(entry_price=20.0, sl_pts=3.12, side="SELL")
    assert trigger_sell == 23.10

    # Deep stop cannot be <= 0
    trigger_floor = dispatcher.calculate_stop_trigger(entry_price=5.0, sl_pts=10.0, side="BUY")
    assert trigger_floor == 0.05


def test_live_gtt_dispatch_and_cancel_on_target():
    mock_broker = MockGTTBroker(should_fail=False)
    dispatcher = GTTStopDispatcher(broker_adapter=mock_broker, enable_live_dispatch=True)

    resp = dispatcher.dispatch_stop_on_entry_fill(
        index_name="NIFTY",
        symbol="NIFTY 25450 CE",
        instrument_token="NSE_FO|45409",
        entry_price=25.0,
        sl_pts=4.0,
        qty=75,
        parent_order_id="ORD_12345",
    )

    assert resp.success is True
    assert resp.gtt_order_id == "GTT_1"
    assert resp.status == "ACTIVE"
    assert len(mock_broker.placed_orders) == 1

    # Now simulate target hit -> cancel GTT stop order
    cancelled = dispatcher.cancel_on_target_exit("NIFTY 25450 CE")
    assert cancelled is True
    assert "GTT_1" in mock_broker.cancelled_orders
    assert "NIFTY 25450 CE" not in dispatcher.symbol_to_gtt_id


def test_vector10_emergency_abort_on_gtt_rejection():
    """Vector 10: If broker rejects GTT stop order, invoke synchronous
    abort_entry_fill_immediately(symbol, qty, reason) to square off entry fill and avoid naked risk.
    """
    mock_broker = MockGTTBroker(should_fail=True)
    aborted_fills = []

    def mock_abort_cb(symbol, qty, reason):
        aborted_fills.append((symbol, qty, reason))
        return True

    dispatcher = GTTStopDispatcher(
        broker_adapter=mock_broker,
        abort_fill_cb=mock_abort_cb,
        enable_live_dispatch=True,
    )

    resp = dispatcher.dispatch_stop_on_entry_fill(
        index_name="NIFTY",
        symbol="NIFTY 25450 CE",
        instrument_token="NSE_FO|45409",
        entry_price=25.0,
        sl_pts=5.0,
        qty=75,
    )

    assert resp.success is False
    assert resp.status == "REJECTED"
    assert resp.fallback_local_kill is True
    assert len(aborted_fills) == 1
    assert aborted_fills[0][0] == "NIFTY 25450 CE"
    assert aborted_fills[0][1] == 75
    assert "timeout" in aborted_fills[0][2] or "failed" in aborted_fills[0][2].lower()


def test_vector11_prepare_target_exit_cancels_gtt_and_guards_double_fill():
    """Vector 11: Cancel-Before-Target-Exit / Double-Fill Guard.
    prepare_target_exit(symbol: str) -> Tuple[bool, str].
    Must cancel broker GTT stop and verify cancellation ack before permitting target exit release.
    """
    # 1. Successful GTT placement and subsequent prepare_target_exit
    mock_broker = MockGTTBroker(should_fail=False)
    dispatcher = GTTStopDispatcher(broker_adapter=mock_broker, enable_live_dispatch=True)

    resp = dispatcher.dispatch_stop_on_entry_fill(
        index_name="NIFTY",
        symbol="NIFTY 25450 CE",
        instrument_token="NSE_FO|45409",
        entry_price=25.0,
        sl_pts=4.0,
        qty=75,
    )
    assert resp.success is True
    assert "NIFTY 25450 CE" in dispatcher.symbol_to_gtt_id

    # prepare_target_exit should cancel GTT stop order and permit exit
    permitted, msg = dispatcher.prepare_target_exit("NIFTY 25450 CE")
    assert permitted is True
    assert "permitted" in msg.lower()
    assert "NIFTY 25450 CE" not in dispatcher.symbol_to_gtt_id

    # 2. When broker cancel fails, target exit must be BLOCKED
    dispatcher2 = GTTStopDispatcher(broker_adapter=mock_broker, enable_live_dispatch=True)
    resp2 = dispatcher2.dispatch_stop_on_entry_fill(
        index_name="NIFTY",
        symbol="NIFTY 25450 CE",
        instrument_token="NSE_FO|45409",
        entry_price=25.0,
        sl_pts=4.0,
        qty=75,
    )
    assert resp2.success is True

    # Force cancel failure
    mock_broker.should_fail = True
    permitted2, msg2 = dispatcher2.prepare_target_exit("NIFTY 25450 CE")
    assert permitted2 is False
    assert "BLOCKED" in msg2


def test_broker_failure_engages_local_kill_switch():
    mock_broker = MockGTTBroker(should_fail=True)
    fallback_invocations = []

    def mock_kill_switch_cb(sym, price):
        fallback_invocations.append((sym, price))

    dispatcher = GTTStopDispatcher(
        broker_adapter=mock_broker,
        local_kill_switch_cb=mock_kill_switch_cb,
        enable_live_dispatch=True,
    )

    resp = dispatcher.dispatch_stop_on_entry_fill(
        index_name="NIFTY",
        symbol="NIFTY 25450 CE",
        instrument_token="NSE_FO|45409",
        entry_price=25.0,
        sl_pts=5.0,
        qty=75,
    )

    assert resp.success is False
    assert resp.status in {"FALLBACK_LOCAL", "REJECTED"}
    assert resp.fallback_local_kill is True
    assert len(fallback_invocations) == 1
    assert fallback_invocations[0][0] == "NIFTY 25450 CE"
    assert fallback_invocations[0][1] == 20.0  # 25 - 5
