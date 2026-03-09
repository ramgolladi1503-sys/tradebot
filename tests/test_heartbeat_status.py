from __future__ import annotations

from core.heartbeat_status import derive_cycle_semantics


def test_derive_cycle_semantics_market_closed_returns_explicit_market_closed_fields():
    payload = derive_cycle_semantics(
        market_mode="SIM",
        market_open=False,
        suggestion_count=0,
        blocker_counts={},
        last_error="",
    )

    assert payload["semantic_state"] == "market_closed"
    assert payload["dominant_reason"] == "MARKET_CLOSED"
    assert payload["subreason"] == ""
    assert payload["primary_blocker"] == "MARKET_CLOSED"
    assert payload["market_mode"] == "OFFHOURS"
    assert payload["market_open"] is False


def test_derive_cycle_semantics_blocked_uses_dominant_blocker_for_live_open_cycles():
    payload = derive_cycle_semantics(
        market_mode="LIVE",
        market_open=True,
        suggestion_count=0,
        blocker_counts={"NO_LIVE_OPTION_FEED": 2, "PRICE_MISMATCH": 1},
        last_error="",
    )

    assert payload["semantic_state"] == "blocked"
    assert payload["dominant_reason"] == "candidates_blocked"
    assert payload["subreason"] == "NO_LIVE_OPTION_FEED"
    assert payload["primary_blocker"] == "NO_LIVE_OPTION_FEED"
    assert payload["market_mode"] == "LIVE"
    assert payload["market_open"] is True


def test_derive_cycle_semantics_ok_when_suggestions_exist():
    payload = derive_cycle_semantics(
        market_mode="LIVE",
        market_open=True,
        suggestion_count=1,
        blocker_counts={"NO_LIVE_OPTION_FEED": 2},
        last_error="",
    )

    assert payload["semantic_state"] == "ok"
    assert payload["dominant_reason"] == "suggestions_generated"
    assert payload["subreason"] == ""
    assert payload["primary_blocker"] is None
    assert payload["market_mode"] == "LIVE"
    assert payload["market_open"] is True


def test_derive_cycle_semantics_error_wins_over_other_states():
    payload = derive_cycle_semantics(
        market_mode="LIVE",
        market_open=False,
        suggestion_count=0,
        blocker_counts={"NO_LIVE_OPTION_FEED": 2},
        last_error="cycle exploded",
    )

    assert payload["semantic_state"] == "error"
    assert payload["dominant_reason"] == "cycle_error"
    assert payload["subreason"] == "cycle exploded"
    assert payload["primary_blocker"] == "cycle exploded"
