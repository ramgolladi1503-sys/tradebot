"""HOTFIX/EDGE-79B market-close feed state classifier tests."""

from __future__ import annotations

from core.market_close_feed_state import (
    CLOSE_WINDOW_TICK_SLOWDOWN,
    CYCLE_LATENCY_STALE,
    FEED_STATE_HEALTHY,
    FEED_STATE_UNKNOWN,
    LTP_STALE,
    MARKET_CLOSED,
    OPTION_FEED_STALE,
    WEBSOCKET_DISCONNECTED,
    classify_market_close_feed_state,
)


def test_websocket_disconnected_is_distinct_state():
    decision = classify_market_close_feed_state(
        {
            "ws_connected": False,
            "ltp_age_sec": 0.5,
            "option_feed_age_sec": 0.5,
            "cycle_latency_sec": 0.2,
        },
        now_epoch=1_000.0,
    )

    assert decision.state == WEBSOCKET_DISCONNECTED
    assert decision.feed_ok is False
    assert decision.ws_connected is False
    assert decision.decision_gate_reason == WEBSOCKET_DISCONNECTED
    assert WEBSOCKET_DISCONNECTED in decision.blockers


def test_ltp_stale_with_websocket_connected_is_not_socket_disconnect():
    decision = classify_market_close_feed_state(
        {
            "ws_connected": True,
            "ltp_age_sec": 9.0,
            "option_feed_age_sec": 0.5,
            "cycle_latency_sec": 0.2,
            "seconds_to_close": 900.0,
        },
        now_epoch=1_000.0,
        max_ltp_age_sec=2.5,
    )

    assert decision.state == LTP_STALE
    assert decision.feed_ok is False
    assert decision.ws_connected is True
    assert decision.websocket_ok is True
    assert decision.ltp_age_sec == 9.0
    assert decision.decision_gate_reason == LTP_STALE
    assert WEBSOCKET_DISCONNECTED not in decision.blockers


def test_close_window_tick_slowdown_explains_stale_ltp_near_close():
    decision = classify_market_close_feed_state(
        {
            "ws_connected": True,
            "ltp_age_sec": 8.0,
            "option_feed_age_sec": 0.5,
            "cycle_latency_sec": 0.2,
            "seconds_to_close": 120.0,
        },
        now_epoch=1_000.0,
        max_ltp_age_sec=2.5,
        close_window_sec=300.0,
    )

    assert decision.state == CLOSE_WINDOW_TICK_SLOWDOWN
    assert decision.feed_ok is True
    assert decision.ws_connected is True
    assert decision.close_window_active is True
    assert decision.decision_gate_reason == CLOSE_WINDOW_TICK_SLOWDOWN
    assert decision.blockers == ()
    assert decision.warnings == (CLOSE_WINDOW_TICK_SLOWDOWN,)
    assert WEBSOCKET_DISCONNECTED not in decision.blockers


def test_option_feed_stale_is_distinct_from_underlying_ltp_stale():
    decision = classify_market_close_feed_state(
        {
            "ws_connected": True,
            "ltp_age_sec": 0.5,
            "option_feed_age_sec": 9.0,
            "cycle_latency_sec": 0.2,
            "seconds_to_close": 900.0,
        },
        now_epoch=1_000.0,
        max_option_feed_age_sec=3.0,
    )

    assert decision.state == OPTION_FEED_STALE
    assert decision.feed_ok is False
    assert decision.option_feed_age_sec == 9.0
    assert decision.decision_gate_reason == OPTION_FEED_STALE
    assert OPTION_FEED_STALE in decision.blockers
    assert LTP_STALE not in decision.blockers


def test_cycle_latency_stale_precedes_tick_age_classification():
    decision = classify_market_close_feed_state(
        {
            "ws_connected": True,
            "ltp_age_sec": 9.0,
            "option_feed_age_sec": 9.0,
            "cycle_latency_sec": 20.0,
            "seconds_to_close": 900.0,
        },
        now_epoch=1_000.0,
        max_cycle_latency_sec=5.0,
    )

    assert decision.state == CYCLE_LATENCY_STALE
    assert decision.feed_ok is False
    assert decision.cycle_latency_sec == 20.0
    assert decision.decision_gate_reason == CYCLE_LATENCY_STALE
    assert CYCLE_LATENCY_STALE in decision.blockers


def test_market_closed_precedes_feed_staleness():
    decision = classify_market_close_feed_state(
        {
            "market_state": "CLOSED",
            "ws_connected": True,
            "ltp_age_sec": 99.0,
            "option_feed_age_sec": 99.0,
            "cycle_latency_sec": 99.0,
        },
        now_epoch=1_000.0,
    )

    assert decision.state == MARKET_CLOSED
    assert decision.feed_ok is False
    assert decision.market_closed is True
    assert decision.decision_gate_reason == MARKET_CLOSED
    assert MARKET_CLOSED in decision.blockers


def test_healthy_feed_state_when_all_inputs_fresh():
    decision = classify_market_close_feed_state(
        {
            "ws_connected": True,
            "ltp_age_sec": 0.4,
            "option_feed_age_sec": 0.8,
            "cycle_latency_sec": 0.2,
            "seconds_to_close": 1_800.0,
        },
        now_epoch=1_000.0,
    )
    payload = decision.to_payload()

    assert decision.state == FEED_STATE_HEALTHY
    assert decision.feed_ok is True
    assert decision.blockers == ()
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False


def test_empty_payload_fails_unknown_without_side_effects():
    decision = classify_market_close_feed_state({}, now_epoch=1_000.0)

    assert decision.state == FEED_STATE_UNKNOWN
    assert decision.feed_ok is False
    assert decision.decision_gate_reason == FEED_STATE_UNKNOWN
    assert FEED_STATE_UNKNOWN in decision.blockers
    assert decision.read_only is True
    assert decision.append is False


# ---------------------------------------------------------------------------
# WI-14 Invariant Proof Gates: End-of-Day Reconciliation & Clean Session Handoff
# ---------------------------------------------------------------------------

from core.market_close_feed_state import reconcile_eod_session


def test_wi14_gate1_market_close_precedes_websocket_drop_and_schedule_decoupling():
    """seconds_to_close <= 0.0 or market_closed=True evaluates to MARKET_CLOSED, even if ws_connected=False (I-1)."""
    # Simultaneous market close and socket drop
    decision = classify_market_close_feed_state(
        {
            "ws_connected": False,
            "websocket_ok": False,
            "seconds_to_close": 0.0,
            "ltp_age_sec": 10.0,
        },
        now_epoch=1_000.0,
    )
    assert decision.state == MARKET_CLOSED
    assert decision.decision_gate_reason == MARKET_CLOSED
    assert decision.feed_ok is False

    # Negative seconds_to_close (e.g. 15:35 IST or special session close)
    decision_neg = classify_market_close_feed_state(
        {
            "ws_connected": False,
            "seconds_to_close": -300.0,
        },
        now_epoch=1_000.0,
    )
    assert decision_neg.state == MARKET_CLOSED


def test_wi14_gate2_eod_reconciliation_read_only_and_order_safety():
    """EOD reconciliation never places/cancels orders; open orders flag UNRECONCILED_OPEN_ORDERS_DETECTED (I-2)."""
    # Clean case
    clean_res = reconcile_eod_session(session_date="2026-10-14", market_closed=True)
    assert clean_res.reconciliation_state == "RECONCILED_CLEAN"
    assert clean_res.read_only is True
    assert clean_res.is_order_action is False
    assert clean_res.broker_api_called is False
    assert clean_res.allowed_for_live_execution is False

    # Case with open orders: MUST NOT attempt order actions, flags advisory warning
    open_orders_mock = [{"order_id": "ORD-12345", "status": "OPEN", "symbol": "NIFTY26OCT24800CE"}]
    warn_res = reconcile_eod_session(
        session_date="2026-10-14",
        market_closed=True,
        open_orders=open_orders_mock,
    )
    assert warn_res.reconciliation_state == "UNRECONCILED_OPEN_ORDERS_DETECTED"
    assert "UNRECONCILED_OPEN_ORDERS_DETECTED" in warn_res.warnings
    assert warn_res.open_orders_count == 1
    assert warn_res.is_order_action is False
    assert warn_res.broker_api_called is False


def test_wi14_gate3_bridge_certify_eod_drain_behavior():
    """LiveSourceRuntimeBridge.certify_eod_drain behaviorally verifies queue depth == 0 (I-4)."""
    from core.market_event_graph_live_runtime_bridge import LiveSourceRuntimeBridge

    bridge = LiveSourceRuntimeBridge()
    certified, depth, dropped = bridge.certify_eod_drain()
    assert certified is True
    assert depth == 0
    assert dropped == 0


def test_wi14_gate4_session_handoff_manifest_export_and_immutability():
    """Session Handoff Manifest produces a verifiable SHA256 sealed payload (I-3, I-4)."""
    from core.market_event_graph_live_runtime_bridge import LiveSourceRuntimeBridge

    bridge = LiveSourceRuntimeBridge()
    recon = reconcile_eod_session(session_date="2026-10-14", market_closed=True)
    manifest = bridge.build_session_handoff_manifest(recon, session_date="2026-10-14")

    assert manifest["session_date"] == "2026-10-14"
    assert manifest["handoff_status"] == "CLEAN_HANDOFF_CERTIFIED"
    assert manifest["queue_drain_certified"] is True
    assert manifest["remaining_queue_depth"] == 0
    assert manifest["dropped_evidence_writes"] == 0
    assert len(manifest["manifest_sha256"]) == 64  # valid SHA256 hex
    assert manifest["read_only"] is True
    assert manifest["is_order_action"] is False
    assert manifest["broker_api_called"] is False
    assert manifest["allowed_for_live_execution"] is False


def test_wi14_gate5_dirty_handoff_when_dropped_writes_occur():
    """If dropped writes occurred, session handoff manifest flags DIRTY_HANDOFF_UNRESOLVED_WRITES (I-4)."""
    from core.market_event_graph_live_runtime_bridge import LiveSourceRuntimeBridge

    bridge = LiveSourceRuntimeBridge()
    bridge._dropped_evidence_writes = 2  # simulate 2 dropped writes
    recon = reconcile_eod_session(session_date="2026-10-14", market_closed=True)
    manifest = bridge.build_session_handoff_manifest(recon, session_date="2026-10-14")

    assert manifest["handoff_status"] == "DIRTY_HANDOFF_UNRESOLVED_WRITES"
    assert manifest["dropped_evidence_writes"] == 2
    assert manifest["queue_drain_certified"] is False
