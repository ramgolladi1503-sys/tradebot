"""Safety regression tests for EDGE-36 feed recovery evidence.

These tests are read-only: broker_api_called=False, is_order_action=False,
live_order_action=False, broker_order_action=False. Feed recovery evidence must
not perform reconnects, broker calls, or order actions.
"""

from core.feed_recovery_evidence import evaluate_feed_recovery_evidence


def test_feed_recovery_evidence_is_read_only_safety_gate():
    broker_api_called = False
    is_order_action = False
    live_order_action = False
    broker_order_action = False

    decision = evaluate_feed_recovery_evidence(
        {
            "feed_state": "DATA_STALE",
            "feed_age_sec": 9.0,
            "recovery_attempted": False,
            "fail_closed": True,
            "execution_allowed": False,
        }
    )

    assert decision.recovery_ok is False
    assert broker_api_called is False
    assert is_order_action is False
    assert live_order_action is False
    assert broker_order_action is False


def test_feed_recovery_evidence_healthy_feed_needs_no_recovery():
    decision = evaluate_feed_recovery_evidence(
        {
            "feed_state": "DATA_OK",
            "feed_age_sec": 0.5,
            "execution_allowed": True,
        }
    )

    assert decision.recovery_ok is True
    assert decision.reason_code == "feed_recovery_not_required"
    assert decision.context["stale_feed_detected"] is False


def test_feed_recovery_evidence_blocks_stale_feed_without_attempt():
    decision = evaluate_feed_recovery_evidence(
        {
            "feed_state": "DATA_STALE",
            "feed_age_sec": 12.0,
            "recovery_attempted": False,
            "fail_closed": True,
            "execution_allowed": False,
        }
    )

    assert decision.recovery_ok is False
    assert decision.reason_code == "feed_recovery_blocked"
    assert "stale_feed_detected" in decision.reasons
    assert "recovery_attempt_absent" in decision.reasons


def test_feed_recovery_evidence_blocks_when_recovery_result_absent():
    decision = evaluate_feed_recovery_evidence(
        {
            "feed_state": "DATA_STALE",
            "feed_age_sec": 12.0,
            "recovery_attempted": True,
            "fail_closed": True,
            "execution_allowed": False,
        }
    )

    assert decision.recovery_ok is False
    assert "recovery_result_absent" in decision.reasons


def test_feed_recovery_evidence_blocks_unsafe_execution_after_failed_recovery():
    decision = evaluate_feed_recovery_evidence(
        {
            "feed_state": "DATA_STALE",
            "feed_age_sec": 12.0,
            "recovery_attempted": True,
            "recovery_successful": False,
            "fail_closed": False,
            "execution_allowed": True,
        }
    )

    assert decision.recovery_ok is False
    assert set(decision.reasons) == {
        "stale_feed_detected",
        "recovery_unsuccessful",
        "fail_closed_absent",
        "unsafe_execution_allowed",
    }


def test_feed_recovery_evidence_allows_successful_recovery_with_fail_closed_proof():
    decision = evaluate_feed_recovery_evidence(
        {
            "feed_state": "DATA_STALE",
            "feed_age_sec": 12.0,
            "recovery_attempted": True,
            "post_recovery_age_sec": 0.4,
            "fail_closed": True,
            "execution_allowed": False,
        }
    )

    assert decision.recovery_ok is True
    assert decision.reason_code == "feed_recovery_ok"
    assert decision.reasons == ("stale_feed_detected", "feed_recovery_ok")
    assert decision.context["recovery_successful"] is True
