from __future__ import annotations

import pytest

from core.option_fill_model import (
    BUY_ENTRY,
    BUY_EXIT,
    FILL_APPROVED,
    FILL_REJECTED,
    OptionFillModelError,
    build_option_fill_decision,
)


def _quote(**overrides):
    payload = {
        "bid": 100.0,
        "ask": 101.0,
        "ltp": 100.5,
        "depth": 1000.0,
        "quote_age_sec": 0.4,
        "fallback_used": False,
        "advisory_only": False,
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def test_buy_entry_fills_at_ask_plus_slippage():
    decision = build_option_fill_decision(
        _quote(bid=100.0, ask=101.0),
        fill_type=BUY_ENTRY,
        quantity=10,
        slippage_pct=0.25,
    )

    assert decision.state == FILL_APPROVED
    assert decision.approved is True
    assert decision.reference_price == 101.0
    assert decision.fill_price == 101.2525
    assert decision.estimated_notional == 1012.525
    assert decision.estimated_slippage_cost == 2.525
    assert decision.blockers == ()
    assert decision.broker_order_action is False
    assert decision.live_order_action is False
    assert decision.is_order_action is False
    assert decision.append is False


def test_buy_exit_fills_at_bid_minus_slippage():
    decision = build_option_fill_decision(
        _quote(bid=100.0, ask=101.0),
        fill_type=BUY_EXIT,
        quantity=10,
        slippage_pct=0.25,
    )

    assert decision.state == FILL_APPROVED
    assert decision.approved is True
    assert decision.reference_price == 100.0
    assert decision.fill_price == 99.75
    assert decision.estimated_notional == 997.5
    assert decision.estimated_slippage_cost == 2.5
    assert decision.blockers == ()


def test_ltp_only_quote_is_rejected():
    decision = build_option_fill_decision(
        {"ltp": 100.5, "depth": 1000.0, "quote_age_sec": 0.4},
        fill_type=BUY_ENTRY,
        quantity=10,
    )

    assert decision.state == FILL_REJECTED
    assert decision.approved is False
    assert decision.fill_price is None
    assert "LTP_ONLY_FILL_REJECTED" in decision.blockers
    assert "QUOTE_BID_MISSING" in decision.blockers
    assert "QUOTE_ASK_MISSING" in decision.blockers


def test_stale_quote_is_rejected():
    decision = build_option_fill_decision(
        _quote(quote_age_sec=9.0),
        fill_type=BUY_ENTRY,
        quantity=10,
        max_quote_age_sec=2.5,
    )

    assert decision.state == FILL_REJECTED
    assert decision.approved is False
    assert "QUOTE_STALE" in decision.blockers


def test_wide_spread_is_rejected():
    decision = build_option_fill_decision(
        _quote(bid=90.0, ask=110.0),
        fill_type=BUY_ENTRY,
        quantity=10,
        max_spread_pct=3.0,
    )

    assert decision.state == FILL_REJECTED
    assert decision.spread_pct == 20.0
    assert "QUOTE_SPREAD_TOO_WIDE" in decision.blockers


def test_missing_depth_is_rejected():
    decision = build_option_fill_decision(
        _quote(depth=None),
        fill_type=BUY_ENTRY,
        quantity=10,
    )

    assert decision.state == FILL_REJECTED
    assert "QUOTE_DEPTH_MISSING" in decision.blockers


def test_low_depth_is_rejected():
    decision = build_option_fill_decision(
        _quote(depth=0.0),
        fill_type=BUY_ENTRY,
        quantity=10,
        min_depth=1.0,
    )

    assert decision.state == FILL_REJECTED
    assert "QUOTE_DEPTH_BELOW_MIN" in decision.blockers


def test_fallback_quote_is_rejected():
    decision = build_option_fill_decision(
        _quote(fallback_used=True),
        fill_type=BUY_ENTRY,
        quantity=10,
    )

    assert decision.state == FILL_REJECTED
    assert "FALLBACK_QUOTE_REJECTED" in decision.blockers


def test_advisory_quote_is_rejected():
    decision = build_option_fill_decision(
        _quote(advisory_only=True),
        fill_type=BUY_ENTRY,
        quantity=10,
    )

    assert decision.state == FILL_REJECTED
    assert "ADVISORY_QUOTE_REJECTED" in decision.blockers


def test_invalid_bid_ask_shape_is_rejected():
    decision = build_option_fill_decision(
        _quote(bid=105.0, ask=100.0),
        fill_type=BUY_ENTRY,
        quantity=10,
    )

    assert decision.state == FILL_REJECTED
    assert "QUOTE_ASK_BELOW_BID" in decision.blockers


def test_zero_quantity_is_rejected():
    decision = build_option_fill_decision(
        _quote(),
        fill_type=BUY_ENTRY,
        quantity=0,
    )

    assert decision.state == FILL_REJECTED
    assert "QUANTITY_MISSING" in decision.blockers


def test_upstream_quote_blockers_are_preserved():
    decision = build_option_fill_decision(
        _quote(blockers=["FEED_NOT_OK"], warnings=["quote_warning"]),
        fill_type=BUY_ENTRY,
        quantity=10,
    )

    assert decision.state == FILL_REJECTED
    assert "FEED_NOT_OK" in decision.blockers
    assert "QUOTE_WARNING" in decision.warnings


def test_unsupported_fill_type_raises():
    with pytest.raises(OptionFillModelError) as exc_info:
        build_option_fill_decision(_quote(), fill_type="SELL_SHORT", quantity=10)

    assert "unsupported_fill_type:SELL_SHORT" in str(exc_info.value)


def test_to_dict_is_json_friendly_and_stable():
    decision = build_option_fill_decision(_quote(), fill_type=BUY_ENTRY, quantity=10)
    payload = decision.to_dict()

    assert payload["schema_version"] == 1
    assert payload["state"] == FILL_APPROVED
    assert payload["fill_type"] == BUY_ENTRY
    assert payload["approved"] is True
    assert payload["broker_order_action"] is False
    assert payload["live_order_action"] is False
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["blockers"] == []
