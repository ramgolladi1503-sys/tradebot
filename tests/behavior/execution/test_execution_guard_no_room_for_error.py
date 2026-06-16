from __future__ import annotations

import time

import pytest

from core.execution.execution_guard import evaluate_execution_guard


pytestmark = [pytest.mark.behavior, pytest.mark.edge, pytest.mark.safety]


def _snapshot(**overrides):
    payload = {
        "ts": time.time(),
        "bid": 100.0,
        "ask": 101.0,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("label", "snapshot", "expected_reason"),
    [
        (
            "missing_timestamp",
            {"bid": 100.0, "ask": 101.0},
            "quote_timestamp_missing",
        ),
        (
            "crossed_book",
            _snapshot(require_depth=True, depth={"buy": [{"price": 101.0}], "sell": [{"price": 100.0}]}),
            "crossed_book",
        ),
        (
            "subscription_failed",
            _snapshot(quote_source="subscription_failed"),
            "fallback_quote",
        ),
        (
            "synthetic_offhours",
            _snapshot(quote_source="synthetic_offhours"),
            "fallback_quote",
        ),
        (
            "recovered_fallback",
            _snapshot(quote_source="recovered_fallback"),
            "fallback_quote",
        ),
        (
            "missing_option_token",
            _snapshot(require_instrument_token=True, instrument_token=None),
            "missing_option_token",
        ),
        (
            "negative_depth_age",
            _snapshot(
                require_depth=True,
                depth={"buy": [{"price": 100.0}], "sell": [{"price": 101.0}]},
                depth_age_sec=-1.0,
            ),
            "negative_depth_age",
        ),
    ],
)
def test_execution_guard_fails_closed_on_no_room_for_error_inputs(label, snapshot, expected_reason):
    """
    Edge purpose:
    Prevents stale, fallback, malformed, or self-contradictory quote evidence from becoming executable.
    """
    now = time.time()
    decision = evaluate_execution_guard(
        side="BUY",
        bid=snapshot.get("bid"),
        ask=snapshot.get("ask"),
        snapshot=snapshot,
        evaluated_at_epoch=now,
        max_quote_age_sec=2.0,
        max_spread_pct=0.05,
    )

    assert decision.execution_allowed is False, label
    assert expected_reason in decision.reasons, label


def test_execution_guard_zero_age_quote_is_still_fresh():
    """
    Edge purpose:
    Preserves genuine fresh quotes so the guard does not over-block healthy execution candidates.
    """
    now = time.time()
    decision = evaluate_execution_guard(
        side="BUY",
        bid=100.0,
        ask=101.0,
        snapshot=_snapshot(ts=now),
        evaluated_at_epoch=now,
        max_quote_age_sec=2.0,
        max_spread_pct=0.05,
        reference_price=101.0,
    )

    assert decision.execution_allowed is True
    assert decision.quote_age_sec == pytest.approx(0.0, abs=0.05)
    assert decision.execution_entry == 101.0
