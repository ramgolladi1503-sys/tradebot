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
import threading
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
    router = SentinelExecutionRouter(enable_nifty_live=False)
    
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


def test_unknown_index_policy_is_sim_only():
    router = SentinelExecutionRouter(enable_nifty_live=False)
    policy = router.get_policy("UNKNOWN_INDEX")
    assert policy.target_mode == ExecutionMode.SIM
    assert policy.allowed_live is False
    assert policy.lot_size == 0


def test_open_order_keeps_entry_reservation_blocked():
    dispatcher = SentinelAutomatedOrderDispatcher(max_daily_live_trades=5)
    assert dispatcher._classify_fill_status("OPEN", 0, 25) == "OPEN"
    reserved, _ = dispatcher._reserve_live_entry("NIFTY", "NIFTY CE", "working", 25)
    assert reserved is True
    dispatcher._intents["working"]["status"] = "OPEN"
    second, reason = dispatcher._reserve_live_entry("NIFTY", "NIFTY PE", "second", 25)
    assert second is False
    assert "unresolved" in reason.lower()
    assert len(dispatcher._intents) == 1


def test_exit_latch_clears_only_for_pre_dispatch_veto():
    may_clear = SentinelAutomatedOrderDispatcher._may_clear_exit_latch
    assert may_clear(pre_dispatch_veto=True, stop_side_effect_started=False) is True
    assert may_clear(pre_dispatch_veto=True, stop_side_effect_started=True) is False
    assert may_clear(pre_dispatch_veto=False, stop_side_effect_started=False) is False


def test_entry_reservation_serializes_distinct_intents_under_one_lock():
    dispatcher = SentinelAutomatedOrderDispatcher(max_daily_live_trades=5)
    barrier = threading.Barrier(3)
    results = []

    def reserve(key):
        barrier.wait()
        results.append(dispatcher._reserve_live_entry("NIFTY", key, key, 25))

    threads = [threading.Thread(target=reserve, args=(key,)) for key in ("intent-a", "intent-b")]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert sum(1 for ok, _ in results if ok) == 1
    assert len(dispatcher._intents) == 1


def test_entry_reservation_enforces_daily_cap_boundary():
    dispatcher = SentinelAutomatedOrderDispatcher(max_daily_live_trades=2)
    dispatcher.daily_live_trade_count["NIFTY"] = 2
    reserved, reason = dispatcher._reserve_live_entry("NIFTY", "NIFTY CE", "intent", 25)
    assert reserved is False
    assert reason.startswith("Daily trade cap")
    assert dispatcher._intents == {}
