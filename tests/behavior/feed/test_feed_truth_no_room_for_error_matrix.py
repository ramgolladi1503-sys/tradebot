from __future__ import annotations

import pytest

from core.feed_health_truth import classify_feed_health_truth


pytestmark = [pytest.mark.behavior, pytest.mark.edge, pytest.mark.regression]


def _payload(**overrides):
    payload = {
        "feed_ok": True,
        "ws_connected": True,
        "effective_ws_connected": True,
        "runtime_state": "RUNNING",
        "state_machine": {"state": "LIVE", "reason": "ticks_flowing"},
        "last_tick_age_sec": 0.5,
        "last_depth_age_sec": 0.5,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_last_tick_age_by_symbol": {"NIFTY": 0.5},
        "symbol_feed_ok_by_symbol": {"NIFTY": True},
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("label", "payload", "expected_reason"),
    [
        (
            "connected_but_underlying_stale",
            _payload(last_tick_age_sec=9.0),
            "ltp_ticks_stale",
        ),
        (
            "option_quote_fresh_but_depth_stale",
            _payload(last_depth_age_sec=12.0),
            "depth_ticks_stale",
        ),
        (
            "option_blocked_with_missing_age",
            _payload(
                option_feed_block_reason_by_symbol={"NIFTY": "NO_LIVE_OPTION_FEED"},
                option_last_tick_age_by_symbol={"NIFTY": None},
            ),
            "NIFTY:option_feed_blocked",
        ),
        (
            "runtime_state_unknown",
            _payload(runtime_state="DEGRADED_UNKNOWN"),
            "runtime_state_unsafe",
        ),
        (
            "websocket_disconnected",
            _payload(ws_connected=False, effective_ws_connected=False),
            "websocket_disconnected",
        ),
    ],
)
def test_feed_truth_fails_closed_for_no_room_for_error_states(label, payload, expected_reason):
    """
    Edge purpose:
    Prevents connected-but-stale, blocked-option, or unsafe runtime feed states from being promoted into executable truth.
    """
    decision = classify_feed_health_truth(
        payload,
        symbols=("NIFTY",),
        max_option_tick_age_sec=2.0,
        max_ltp_age_sec=2.5,
        max_depth_age_sec=6.0,
    )

    assert decision.feed_ok is False, label
    assert expected_reason in decision.reasons, label


def test_feed_truth_healthy_payload_remains_executable_grade():
    """
    Edge purpose:
    Preserves clean live-feed proof so the feed gate does not over-block healthy execution-grade conditions.
    """
    decision = classify_feed_health_truth(
        _payload(),
        symbols=("NIFTY",),
        max_option_tick_age_sec=2.0,
        max_ltp_age_sec=2.5,
        max_depth_age_sec=6.0,
    )

    assert decision.feed_ok is True
    assert decision.reasons == ()
    assert decision.symbols[0].feed_ok is True
