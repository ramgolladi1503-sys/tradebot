"""Synthetic event-tape tests for the isolated reference execution oracle."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from research.verification_gateway.reference_execution import (
    SyntheticDecision,
    SyntheticQuote,
    replay_long_round_trip,
)


T0 = datetime(2026, 9, 27, 9, 15, tzinfo=timezone.utc)


def decision(offset, *, contract="C1", side="BUY", instrument="NIFTY"):
    return SyntheticDecision(T0 + timedelta(minutes=offset), instrument, contract, side)


def quote(offset, bid, ask, *, available_offset=None, contract="C1", instrument="NIFTY"):
    event_time = T0 + timedelta(minutes=offset)
    available_time = T0 + timedelta(minutes=available_offset if available_offset is not None else offset)
    return SyntheticQuote(event_time, available_time, instrument, contract,
                         Decimal(str(bid)), Decimal(str(ask)))


def replay(quotes, *, entry=None, exit=None, fee="5", slip="10"):
    return replay_long_round_trip(
        quotes, entry_decision=entry or decision(1, side="BUY"),
        exit_decision=exit or decision(3, side="SELL"),
        fee_bps=fee, slippage_bps=slip,
    )


def test_next_known_quote_contract_identity_spread_slippage_and_fees():
    result = replay([
        quote(0, 98, 99),  # before signal: not eligible
        quote(1, 99, 101),
        quote(3, 109, 111),
    ])
    assert result.entry.price == Decimal("101.101")
    assert result.exit.price == Decimal("108.891")
    assert result.gross_pnl == Decimal("7.790")
    assert result.total_fees == Decimal("0.104996")
    assert result.net_pnl == Decimal("7.685004")
    assert result.entry.available_time == decision(1).decided_at
    assert result.exit.available_time > result.entry.available_time


def test_wrong_contract_quote_is_skipped():
    result = replay([
        quote(1, 1, 2, contract="OTHER"),
        quote(2, 99, 101),
        quote(3, 109, 111),
    ])
    assert result.entry.event_time == decision(2).decided_at


def test_quote_published_after_event_is_used_only_after_publication():
    result = replay([
        quote(1, 99, 101, available_offset=2),
        quote(3, 109, 111, available_offset=4),
    ])
    assert result.entry.event_time == decision(1).decided_at
    assert result.entry.available_time == decision(2).decided_at


def test_no_post_decision_quote_blocks():
    with pytest.raises(ValueError, match="NO_POST_DECISION_QUOTE"):
        replay([quote(0, 99, 101), quote(2, 109, 111)])


def test_malformed_quote_blocks_even_if_other_quote_is_usable():
    with pytest.raises(ValueError, match="CROSSED_QUOTE"):
        replay([quote(1, 102, 101), quote(3, 109, 111)])


def test_availability_before_event_blocks():
    with pytest.raises(ValueError, match="QUOTE_AVAILABLE_BEFORE_EVENT"):
        replay([quote(1, 99, 101, available_offset=0), quote(3, 109, 111)])


def test_naive_decision_clock_blocks():
    naive = SyntheticDecision(datetime(2026, 9, 27, 9, 16), "NIFTY", "C1", "BUY")
    with pytest.raises(ValueError, match="TIMEZONE_AWARE"):
        replay([quote(1, 99, 101), quote(3, 109, 111)], entry=naive)


def test_non_buy_entry_and_mismatched_contracts_block():
    with pytest.raises(ValueError, match="BUY_ONLY_ENTRY_REQUIRED"):
        replay([quote(1, 99, 101), quote(3, 109, 111)], entry=decision(1, side="SELL"))
    with pytest.raises(ValueError, match="ENTRY_EXIT_CONTRACT_MISMATCH"):
        replay([quote(1, 99, 101, contract="C1"), quote(3, 109, 111, contract="C2")],
               exit=decision(3, contract="C2", side="SELL"))


def test_exit_fill_must_follow_entry_fill():
    with pytest.raises(ValueError, match="NO_POST_DECISION_QUOTE"):
        replay([quote(1, 99, 101), quote(2, 109, 111)], exit=decision(3, side="SELL"))


@pytest.mark.parametrize("fee,slip", [("-1", "0"), ("0", "-1")])
def test_negative_costs_block(fee, slip):
    with pytest.raises(ValueError, match="NEGATIVE_COST_RATE"):
        replay([quote(1, 99, 101), quote(3, 109, 111)], fee=fee, slip=slip)
