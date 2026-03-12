from __future__ import annotations

from core.entry_semantics import build_entry_state


def test_build_entry_state_buy_uses_fresh_ask_for_execution_and_display():
    out = build_entry_state(
        symbol="NIFTY",
        expiry="2026-03-26",
        strike=23000,
        right="CE",
        side="BUY",
        bid=72.2,
        ask=72.8,
        mark=72.5,
        last=72.4,
        quote_age_sec=1.2,
        mode="LIVE",
        allow_stale_quotes=False,
        market_open=True,
        instrument_matches=True,
        quote_source="tick_store",
    )

    assert float(out["execution_entry"]) == 72.8
    assert out["execution_entry_source"] == "ask"
    assert out["execution_entry_status"] == "executable"
    assert float(out["display_entry"]) == 72.8
    assert out["display_entry_source"] == "ask"
    assert out["display_entry_status"] == "displayable"
    assert float(out["entry"]) == 72.8
    assert out["entry_status"] == "displayable"


def test_build_entry_state_sell_uses_fresh_bid_for_execution_and_display():
    out = build_entry_state(
        symbol="NIFTY",
        expiry="2026-03-26",
        strike=23000,
        right="PE",
        side="SELL",
        bid=101.5,
        ask=102.0,
        mark=101.7,
        last=101.8,
        quote_age_sec=1.0,
        mode="LIVE",
        allow_stale_quotes=False,
        market_open=True,
        instrument_matches=True,
        quote_source="tick_store",
    )

    assert float(out["execution_entry"]) == 101.5
    assert out["execution_entry_source"] == "bid"
    assert out["execution_entry_status"] == "executable"
    assert float(out["display_entry"]) == 101.5
    assert out["display_entry_source"] == "bid"
    assert out["display_entry_status"] == "displayable"


def test_build_entry_state_uses_mark_for_display_when_executable_quote_missing():
    out = build_entry_state(
        symbol="NIFTY",
        expiry="2026-03-26",
        strike=23000,
        right="CE",
        side="BUY",
        bid=None,
        ask=None,
        mark=73.1,
        last=72.9,
        quote_age_sec=1.5,
        mode="ADVISORY",
        allow_stale_quotes=True,
        market_open=False,
        instrument_matches=True,
        quote_source="tick_store",
    )

    assert out["execution_entry"] is None
    assert out["execution_entry_status"] == "non_executable"
    assert float(out["display_entry"]) == 73.1
    assert out["display_entry_source"] == "mark"
    assert out["display_entry_status"] == "displayable"
    assert float(out["entry"]) == 73.1
    assert out["entry_status"] == "displayable"


def test_build_entry_state_uses_mid_when_display_only_bid_ask_are_available():
    out = build_entry_state(
        symbol="NIFTY",
        expiry="2026-03-26",
        strike=23000,
        right="CE",
        side="BUY",
        bid=72.0,
        ask=72.4,
        mark=None,
        mid=None,
        last=None,
        quote_age_sec=3.0,
        mode="LIVE",
        allow_stale_quotes=False,
        market_open=True,
        instrument_matches=True,
        quote_source="tick_store",
    )

    assert out["execution_entry"] is None
    assert out["execution_entry_status"] == "non_executable"
    assert float(out["display_entry"]) == 72.2
    assert out["display_entry_source"] == "mid"
    assert out["display_entry_status"] == "displayable"


def test_build_entry_state_uses_last_when_mark_and_mid_missing():
    out = build_entry_state(
        symbol="NIFTY",
        expiry="2026-03-26",
        strike=23000,
        right="CE",
        side="BUY",
        bid=None,
        ask=None,
        mark=None,
        mid=None,
        last=72.9,
        quote_age_sec=1.0,
        mode="ADVISORY",
        allow_stale_quotes=True,
        market_open=False,
        instrument_matches=True,
        quote_source="tick_store",
    )

    assert out["execution_entry"] is None
    assert out["display_entry"] == 72.9
    assert out["display_entry_source"] == "last"
    assert out["display_entry_status"] == "displayable"


def test_build_entry_state_clears_stale_quote_when_all_candidates_expire():
    out = build_entry_state(
        symbol="NIFTY",
        expiry="2026-03-26",
        strike=23000,
        right="CE",
        side="BUY",
        bid=72.0,
        ask=72.8,
        mark=72.5,
        last=72.4,
        quote_age_sec=20.0,
        mode="LIVE",
        allow_stale_quotes=False,
        market_open=True,
        instrument_matches=True,
        quote_source="tick_store",
    )

    assert out["execution_entry"] is None
    assert out["display_entry"] is None
    assert out["entry"] is None
    assert out["entry_status"] == "missing"
    assert out["entry_clear_reason"] == "stale_quote"


def test_build_entry_state_clears_for_instrument_mismatch():
    out = build_entry_state(
        symbol="NIFTY",
        expiry="2026-03-26",
        strike=23000,
        right="CE",
        side="BUY",
        bid=72.0,
        ask=72.8,
        mark=72.5,
        last=72.4,
        quote_age_sec=1.0,
        mode="LIVE",
        allow_stale_quotes=False,
        market_open=True,
        instrument_matches=False,
        quote_source="tick_store",
    )

    assert out["execution_entry"] is None
    assert out["display_entry"] is None
    assert out["entry"] is None
    assert out["entry_status"] == "missing"
    assert out["entry_clear_reason"] == "instrument_mismatch"
