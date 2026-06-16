from __future__ import annotations

import pytest

from core.feed_recovery_runtime import classify_feed_recovery_runtime


pytestmark = [pytest.mark.behavior, pytest.mark.edge, pytest.mark.regression]


def _payload(**updates):
    payload = {
        "market_open": True,
        "feed_ok": False,
        "ws_connected": True,
        "effective_ws_connected": True,
        "runtime_state": "RUNNING",
        "state_machine": {"state": "LIVE", "reason": "ticks_flowing"},
        "subscribed_tokens_count": 24,
        "intended_tokens_count": 24,
        "subscribed_option_tokens_count": 18,
        "missing_option_tokens_count": 0,
        "last_tick_age_sec": 0.5,
        "last_depth_age_sec": 0.8,
        "warmup_clean_cycles": 3,
        "warmup_required_clean_cycles": 3,
        "verified_option_symbols": ["NIFTY"],
        "missing_option_symbols": [],
        "option_ticks_verified": True,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_active_blockers_by_symbol": {"NIFTY": []},
    }
    payload.update(updates)
    return payload


def test_feed_recovery_warmup_does_not_unlock_early():
    """
    Edge purpose:
    Prevents reconnect or warmup states from becoming healthy before clean proof cycles complete.
    """
    decision = classify_feed_recovery_runtime(
        _payload(
            feed_ok=True,
            runtime_state="RECONNECTING",
            warmup_clean_cycles=1,
            warmup_required_clean_cycles=3,
        )
    )

    assert decision.recovery_state == "RECOVERY_PROOF_PENDING"
    assert decision.should_attempt_recovery is False
    assert "WARMUP_INCOMPLETE" in decision.context["full_feed_proof_blockers"]


def test_feed_recovery_resubscription_gap_stays_recovery_candidate():
    """
    Edge purpose:
    Prevents partial subscription recovery from being mislabeled as healthy feed truth.
    """
    decision = classify_feed_recovery_runtime(
        _payload(
            feed_ok=False,
            subscribed_option_tokens_count=0,
            missing_option_tokens_count=5,
        )
    )

    assert decision.recovery_state == "OPTION_SUBSCRIPTIONS_MISSING"
    assert decision.action_hint == "option_resubscribe_candidate"
    assert decision.should_attempt_recovery is True


def test_feed_recovery_websocket_drop_requires_full_restart_candidate():
    """
    Edge purpose:
    Prevents websocket disconnect states from being treated as advisory-only or safe-to-trade.
    """
    decision = classify_feed_recovery_runtime(
        _payload(
            ws_connected=False,
            effective_ws_connected=False,
            state_machine={"state": "DOWN", "reason": "ws_disconnected"},
        )
    )

    assert decision.recovery_state == "WS_DISCONNECTED"
    assert decision.force_full_restart is True
    assert decision.should_attempt_recovery is True


def test_feed_recovery_clean_feed_proof_stays_healthy():
    """
    Edge purpose:
    Preserves real healthy feed states so the recovery classifier does not over-block after verified recovery.
    """
    decision = classify_feed_recovery_runtime(_payload(feed_ok=True))

    assert decision.recovery_state == "HEALTHY"
    assert decision.should_attempt_recovery is False
    assert decision.context["full_feed_proof_ready"] is True
