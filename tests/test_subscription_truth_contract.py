import json

from core.subscription_truth_contract import (
    SUBSCRIPTION_TRUTH_BLOCKED,
    SUBSCRIPTION_TRUTH_OK,
    SUBSCRIPTION_TRUTH_RESUBSCRIBE_VERIFIED,
    build_subscription_truth_contract,
)


def _payload(**overrides):
    payload = {
        "subscription_state": "VERIFIED",
        "verification_state": "VERIFIED",
        "intended_tokens_count": 10,
        "subscribed_tokens_count": 10,
        "subscribed_option_tokens_count": 10,
        "missing_option_tokens_count": 0,
        "verified_option_symbols": ["NIFTY", "BANKNIFTY"],
        "missing_option_symbols": [],
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK", "BANKNIFTY": "OK"},
        "option_last_tick_age_by_symbol": {"NIFTY": 0.5, "BANKNIFTY": 0.7},
    }
    payload.update(overrides)
    return payload


def test_subscription_truth_is_read_only_and_non_action():
    contract = build_subscription_truth_contract(_payload())

    assert contract.read_only is True
    assert contract.append is False
    assert contract.is_order_action is False
    assert contract.broker_api_called is False
    assert contract.subscription_truth_ok is True
    assert contract.truth_state == SUBSCRIPTION_TRUTH_OK


def test_subscription_truth_blocks_missing_subscription_counts():
    contract = build_subscription_truth_contract(_payload(subscribed_option_tokens_count=0))

    assert contract.subscription_truth_ok is False
    assert contract.truth_state == SUBSCRIPTION_TRUTH_BLOCKED
    assert "NO_SUBSCRIBED_OPTION_TOKENS" in contract.blockers


def test_resubscribe_verification_requires_verified_completion():
    contract = build_subscription_truth_contract(
        _payload(
            subscription_state="RESUBSCRIBING",
            verification_state="IN_PROGRESS",
            resubscribe_attempted=True,
            resubscribe_successful=False,
        )
    )

    assert contract.subscription_truth_ok is False
    assert contract.truth_state == SUBSCRIPTION_TRUTH_BLOCKED
    assert "RESUBSCRIBE_FAILED" in contract.blockers


def test_resubscribe_verification_reports_verified_when_counts_and_freshness_match():
    contract = build_subscription_truth_contract(
        _payload(
            subscription_state="VERIFIED",
            verification_state="VERIFIED",
            resubscribe_attempted=True,
            resubscribe_successful=True,
        )
    )

    payload = json.loads(json.dumps(contract.to_payload(), sort_keys=True))

    assert contract.subscription_truth_ok is True
    assert contract.resubscribe_verified is True
    assert contract.truth_state == SUBSCRIPTION_TRUTH_RESUBSCRIBE_VERIFIED
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False

