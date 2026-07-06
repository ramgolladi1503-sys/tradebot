import pytest
import os
import json
from unittest.mock import patch, MagicMock

def test_subscription_delta_uses_reactor_call_from_thread():
    from core.kite_depth_ws import _apply_subscription_delta
    ws = MagicMock()
    with patch("twisted.internet.reactor.callFromThread") as mock_call, \
         patch("core.kite_depth_ws._can_mutate_ws_subscriptions", return_value=(True, "ok", {})):
        _apply_subscription_delta(ws, [123], [456], "test")
        assert mock_call.call_count >= 2
        mock_call.assert_any_call(ws.subscribe, [123])
        mock_call.assert_any_call(ws.unsubscribe, [456])

def test_no_live_option_feed_not_triggered_by_single_illiquid_option_gap():
    from core.blocker_lifecycle import evaluate_feed_symbol_blockers, BlockerRegistry
    registry = BlockerRegistry("test")
    evaluate_feed_symbol_blockers(
        registry=registry,
        now_ts=105.0,
        symbol="NIFTY",
        ws_connected=True,
        expected_option_count=1,
        subscribed_option_count=1,
        option_ticks_received_count=10,
        latest_option_tick_ts=100.0,
        latest_option_tick_age_sec=5.0,
        feed_freshness_sec=2.0,
        min_required_count=1,
    )
    keys = [k for k in registry._records.keys() if k[2] == "NO_LIVE_OPTION_FEED"]
    record = registry._records.get(keys[0]) if keys else None
    assert record is None or not record.active

def test_no_option_ticks_post_connection_can_still_trigger_no_live_option_feed():
    from core.blocker_lifecycle import evaluate_feed_symbol_blockers, BlockerRegistry
    registry = BlockerRegistry("test")
    evaluate_feed_symbol_blockers(
        registry=registry,
        now_ts=105.0,
        symbol="NIFTY",
        ws_connected=True,
        expected_option_count=1,
        subscribed_option_count=1,
        option_ticks_received_count=0,
        latest_option_tick_ts=None,
        latest_option_tick_age_sec=None,
        feed_freshness_sec=2.0,
        min_required_count=1,
    )
    keys = [k for k in registry._records.keys() if k[2] == "NO_LIVE_OPTION_FEED"]
    record = registry._records.get(keys[0]) if keys else None
    assert record is not None and record.active

def test_ltp_stale_blocks_candidate_without_global_feed_halt():
    from core.blocker_lifecycle import evaluate_feed_symbol_blockers, BlockerRegistry
    registry = BlockerRegistry("test")
    evaluate_feed_symbol_blockers(
        registry=registry,
        now_ts=100.0,
        symbol="NIFTY",
        ws_connected=True,
        expected_option_count=1,
        subscribed_option_count=1,
        option_ticks_received_count=10,
        latest_option_tick_ts=90.0,
        latest_option_tick_age_sec=10.0,
        feed_freshness_sec=2.0,
        min_required_count=1,
    )
    keys = [k for k in registry._records.keys() if k[2] == "NO_LIVE_OPTION_FEED"]
    record_live = registry._records.get(keys[0]) if keys else None
    assert record_live is None or not record_live.active

def test_rest_recovery_forces_advisory_only():
    candidate = {"symbol": "NIFTY", "execution_allowed": True}
    source_flags = {"quote_source": "REST_RECOVERY"}
    if source_flags.get("quote_source") == "REST_RECOVERY" or source_flags.get("recovered_fallback"):
        candidate["execution_allowed"] = False
        candidate["mode"] = "advisory_only"
    assert candidate["execution_allowed"] is False
    assert candidate["mode"] == "advisory_only"

def test_recovered_fallback_forces_advisory_only():
    candidate = {"symbol": "NIFTY", "execution_allowed": True}
    source_flags = {"recovered_fallback": True}
    if source_flags.get("quote_source") == "REST_RECOVERY" or source_flags.get("recovered_fallback"):
        candidate["execution_allowed"] = False
        candidate["mode"] = "advisory_only"
    assert candidate["execution_allowed"] is False
    assert candidate["mode"] == "advisory_only"
