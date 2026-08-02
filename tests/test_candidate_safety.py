import pytest
import os
import json
import time
from copy import deepcopy
from unittest.mock import patch, MagicMock


def test_subscription_delta_uses_safe_mutation_interface():
    from core.kite_depth_ws import _apply_subscription_delta

    ws = MagicMock()
    with patch("core.feed.ws_mutation_queue.safe_subscribe_full_mode") as mock_sub, \
         patch("core.feed.ws_mutation_queue.safe_unsubscribe") as mock_unsub, \
         patch("core.kite_depth_ws._can_mutate_ws_subscriptions", return_value=(True, "ok", {})):

        # mock return values (WsMutationResult mock)
        mock_res = MagicMock()
        mock_res.ok = True
        mock_sub.return_value = (mock_res, mock_res)
        mock_unsub.return_value = mock_res

        _apply_subscription_delta(ws, [123], [456], "test")

        assert mock_sub.call_count == 1
        assert mock_sub.call_args[0][0] == ws
        assert mock_sub.call_args[0][1] == [123]

        assert mock_unsub.call_count == 1
        assert mock_unsub.call_args[0][0] == ws
        assert mock_unsub.call_args[0][1] == [456]


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


def test_stale_option_ltp_blocks_candidate_execution_without_triggering_no_live_option_feed():
    from core.blocker_lifecycle import evaluate_feed_symbol_blockers, BlockerRegistry
    from core.opportunity_engine import build_opportunity_score

    registry = BlockerRegistry("test")

    # 1. Show NO_LIVE_OPTION_FEED does NOT trigger for 10s gap
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

    # 2. Show stale quote blocks execution in opportunity engine
    candidate = {
        "symbol": "NIFTY",
        "execution_allowed": True,
        "tradable": True,
        "execution_entry": 100.0,
        "execution_entry_status": "executable",
        "risk_budget_ok": True,
        "risk_budget_reason": "ok",
        "fresh_quote_ok": False,  # This makes it stale
        "primary_blocker": "stale_quote",  # Sometimes explicitly passed
    }
    score_out = build_opportunity_score(candidate)

    assert score_out["candidate_class"] != "EXECUTABLE"
    assert score_out.get("primary_blocker") == "stale_quote"


def test_rest_recovery_forces_non_executable_truth_without_mutating_input():
    from core.opportunity_engine import _base_execution_truth

    candidate = {
        "symbol": "NIFTY",
        "execution_allowed": True,
        "tradable": True,
        "execution_entry": 100.0,
        "execution_entry_status": "executable",
        "source_flags": {"quote_source": "REST_RECOVERY"},
    }
    original = deepcopy(candidate)

    truth = _base_execution_truth(candidate)

    assert truth["execution_truth"] is False
    assert truth["truth_allows_execution"] is False
    assert candidate == original


def test_recovered_fallback_forces_non_executable_truth_without_mutating_input():
    from core.opportunity_engine import _base_execution_truth

    candidate = {
        "symbol": "NIFTY",
        "execution_allowed": True,
        "tradable": True,
        "execution_entry": 100.0,
        "execution_entry_status": "executable",
        "source_flags": {"recovered_fallback": True},
    }
    original = deepcopy(candidate)

    truth = _base_execution_truth(candidate)

    assert truth["execution_truth"] is False
    assert truth["truth_allows_execution"] is False
    assert candidate == original
