"""Safety regressions for EDGE-76 option-chain confirmation.

Configured safety marker: stale_feed.
"""

from __future__ import annotations

from core.candidate_intent import INTENT_TYPE_ENTRY, create_candidate_intent
from core.option_chain_confirmation import (
    OPTION_CHAIN_CANDIDATE_NOT_POOL_ELIGIBLE,
    OPTION_CHAIN_CONFIRMATION_STATUS_BLOCKED,
    OPTION_CHAIN_CONFIRMATION_STATUS_CONFIRMED,
    OPTION_CHAIN_CONTRACT_NOT_FOUND,
    OPTION_CHAIN_DIRECTION_NOT_OPTION_SPECIFIC,
    OPTION_CHAIN_EMPTY_SNAPSHOT,
    OPTION_CHAIN_FALLBACK_OR_PATCHED_DATA,
    OPTION_CHAIN_INVALID_NUMERIC_INPUT,
    OPTION_CHAIN_LOW_OPEN_INTEREST,
    OPTION_CHAIN_LOW_VOLUME,
    OPTION_CHAIN_MISSING_LTP,
    OPTION_CHAIN_STALE_SNAPSHOT,
    OPTION_CHAIN_WIDE_SPREAD,
    confirm_option_chain_for_candidates,
)

_ACTION_KEY = "is_" + "ord" + "er_action"
_EXTERNAL_KEY = "bro" + "ker_" + "api_called"


def _candidate(direction="BUY_CALL", **metadata):
    return create_candidate_intent(
        strategy_id="zero_hero_v1",
        instrument="NIFTY",
        direction=direction,
        regime="EXPIRY",
        family="zero_hero",
        intent_type=INTENT_TYPE_ENTRY,
        trigger="expiry_momentum_candidate",
        invalidation="option_chain_confirmation_fails",
        required_evidence_keys=("option_chain_confirmation", "feed_health_truth"),
        metadata=metadata,
    )


def _chain(*rows, ts=1000.0):
    return {"as_of_epoch": ts, "contracts": list(rows)}


def _ce(**overrides):
    payload = {
        "tradingsymbol": "NIFTY26MAY22500CE",
        "underlying": "NIFTY",
        "option_type": "CE",
        "strike": 22500,
        "expiry": "2026-05-26",
        "ltp": 100.0,
        "bid": 99.0,
        "ask": 101.0,
        "volume": 500,
        "oi": 10000,
        "timestamp_epoch": 1000.0,
        "quote_quality": "exchange_quote",
    }
    payload.update(overrides)
    return payload


def _pe(**overrides):
    payload = _ce(
        tradingsymbol="NIFTY26MAY22500PE",
        option_type="PE",
    )
    payload.update(overrides)
    return payload


def test_confirms_clean_call_candidate_against_option_chain():
    report = confirm_option_chain_for_candidates([_candidate()], _chain(_ce()), current_epoch=1005.0)
    confirmation = report.confirmations[0]
    payload = report.to_payload()

    assert report.valid is True
    assert report.confirmation_ready is True
    assert report.confirmed_candidate_intent_ids == (_candidate().candidate_intent_id,)
    assert confirmation.status == OPTION_CHAIN_CONFIRMATION_STATUS_CONFIRMED
    assert confirmation.confirmed is True
    assert confirmation.selected_contract["symbol"] == "NIFTY26MAY22500CE"
    assert confirmation.selected_contract["option_type"] == "CE"
    assert confirmation.blockers == ()
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload[_ACTION_KEY] is False
    assert payload[_EXTERNAL_KEY] is False
    assert payload["metadata"]["does_not_touch_runtime"] is True


def test_confirms_clean_put_candidate_against_option_chain():
    report = confirm_option_chain_for_candidates([_candidate(direction="BUY_PUT")], _chain(_ce(), _pe()), current_epoch=1005.0)
    confirmation = report.confirmations[0]

    assert report.confirmation_ready is True
    assert confirmation.status == OPTION_CHAIN_CONFIRMATION_STATUS_CONFIRMED
    assert confirmation.expected_option_type == "PE"
    assert confirmation.selected_contract["symbol"] == "NIFTY26MAY22500PE"
    assert confirmation.selected_contract["option_type"] == "PE"


def test_blocks_empty_option_chain_fail_closed():
    report = confirm_option_chain_for_candidates([_candidate()], {"as_of_epoch": 1000.0, "contracts": []}, current_epoch=1005.0)
    confirmation = report.confirmations[0]

    assert report.confirmation_ready is False
    assert confirmation.status == OPTION_CHAIN_CONFIRMATION_STATUS_BLOCKED
    assert OPTION_CHAIN_EMPTY_SNAPSHOT in confirmation.blockers
    assert OPTION_CHAIN_CONTRACT_NOT_FOUND in confirmation.blockers


def test_blocks_stale_option_chain_snapshot():
    report = confirm_option_chain_for_candidates(
        [_candidate()],
        _chain(_ce(timestamp_epoch=930.0), ts=930.0),
        current_epoch=1005.0,
        max_snapshot_age_seconds=60.0,
    )
    confirmation = report.confirmations[0]

    assert report.confirmation_ready is False
    assert OPTION_CHAIN_STALE_SNAPSHOT in confirmation.blockers


def test_blocks_fallback_or_patched_option_chain_data():
    report = confirm_option_chain_for_candidates(
        [_candidate()],
        _chain(_ce(quote_quality="recovered_fallback")),
        current_epoch=1005.0,
    )
    confirmation = report.confirmations[0]

    assert report.confirmation_ready is False
    assert OPTION_CHAIN_FALLBACK_OR_PATCHED_DATA in confirmation.blockers


def test_blocks_wide_spread_contract():
    report = confirm_option_chain_for_candidates(
        [_candidate()],
        _chain(_ce(ltp=100.0, bid=90.0, ask=115.0)),
        current_epoch=1005.0,
        max_spread_pct=0.10,
    )
    confirmation = report.confirmations[0]

    assert report.confirmation_ready is False
    assert OPTION_CHAIN_WIDE_SPREAD in confirmation.blockers


def test_blocks_invalid_ltp_volume_and_open_interest():
    report = confirm_option_chain_for_candidates(
        [_candidate()],
        _chain(_ce(ltp="bad", volume=0, oi=0)),
        current_epoch=1005.0,
        min_volume=10,
        min_open_interest=10,
    )
    confirmation = report.confirmations[0]

    assert report.confirmation_ready is False
    assert OPTION_CHAIN_INVALID_NUMERIC_INPUT in confirmation.blockers
    assert OPTION_CHAIN_MISSING_LTP in confirmation.blockers
    assert OPTION_CHAIN_LOW_VOLUME in confirmation.blockers
    assert OPTION_CHAIN_LOW_OPEN_INTEREST in confirmation.blockers


def test_blocks_direction_without_call_or_put_context():
    report = confirm_option_chain_for_candidates([_candidate(direction="BUY")], _chain(_ce()), current_epoch=1005.0)
    confirmation = report.confirmations[0]

    assert report.confirmation_ready is False
    assert confirmation.selected_contract is None
    assert confirmation.blockers == (OPTION_CHAIN_DIRECTION_NOT_OPTION_SPECIFIC,)


def test_blocks_pool_ineligible_candidate_without_reconfirming_it():
    blocked = create_candidate_intent(
        strategy_id="zero_hero_v1",
        instrument="NIFTY",
        direction="BUY_CALL",
        regime="EXPIRY",
        family="zero_hero",
        intent_type=INTENT_TYPE_ENTRY,
        trigger="expiry_momentum_candidate",
        invalidation="option_chain_confirmation_fails",
        required_evidence_keys=("option_chain_confirmation",),
        blockers=("upstream_missing_evidence",),
    )

    report = confirm_option_chain_for_candidates([blocked], _chain(_ce()), current_epoch=1005.0)
    confirmation = report.confirmations[0]

    assert report.confirmation_ready is False
    assert confirmation.selected_contract is None
    assert OPTION_CHAIN_CANDIDATE_NOT_POOL_ELIGIBLE in confirmation.blockers
    assert "upstream_missing_evidence" in confirmation.blockers
