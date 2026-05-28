import json

import pytest

from core.backtest_replay_clock import (
    REASON_CANDLE_FIELD_IN_FUTURE,
    REASON_FULL_SESSION_AGGREGATE_UNAVAILABLE,
    REASON_LOOKBACK_EXCEEDED,
    REASON_NON_MONOTONIC_ADVANCE,
    REASON_NON_MONOTONIC_REPLAY_DATA,
    REASON_SNAPSHOT_IN_FUTURE,
    ReplayClockContractError,
    build_replay_clock,
    validate_monotonic_replay_timestamps,
    visible_snapshots,
)


SESSION_START = "2026-05-28T09:15:00+05:30"
SESSION_END = "2026-05-28T15:30:00+05:30"


def test_replay_clock_starts_at_configured_session_timestamp():
    clock = build_replay_clock(session_start=SESSION_START, session_end=SESSION_END, lookback_seconds=300)

    assert clock.current_timestamp.isoformat() == "2026-05-28T03:45:00+00:00"
    payload = clock.snapshot_access("2026-05-28T09:15:00+05:30").to_payload()
    assert payload["allowed"] is True
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert json.dumps(payload, sort_keys=True)


def test_replay_clock_advances_monotonically_and_rejects_regression():
    clock = build_replay_clock(
        session_start=SESSION_START,
        session_end=SESSION_END,
        current_timestamp="2026-05-28T09:20:00+05:30",
        lookback_seconds=600,
    )

    advanced = clock.advance_to("2026-05-28T09:21:00+05:30")
    assert advanced.current_timestamp.isoformat() == "2026-05-28T03:51:00+00:00"

    with pytest.raises(ReplayClockContractError, match=REASON_NON_MONOTONIC_ADVANCE):
        advanced.advance_to("2026-05-28T09:20:59+05:30")


def test_future_snapshot_access_is_blocked_and_same_timestamp_is_allowed():
    clock = build_replay_clock(
        session_start=SESSION_START,
        session_end=SESSION_END,
        current_timestamp="2026-05-28T09:30:00+05:30",
        lookback_seconds=900,
    )

    assert clock.snapshot_access("2026-05-28T09:30:00+05:30").allowed is True

    future = clock.snapshot_access("2026-05-28T09:30:01+05:30")
    assert future.blocked is True
    assert future.reason == REASON_SNAPSHOT_IN_FUTURE


def test_past_snapshots_are_allowed_only_within_lookback_policy():
    clock = build_replay_clock(
        session_start=SESSION_START,
        session_end=SESSION_END,
        current_timestamp="2026-05-28T09:30:00+05:30",
        lookback_seconds=300,
    )

    assert clock.snapshot_access("2026-05-28T09:25:00+05:30").allowed is True

    old = clock.snapshot_access("2026-05-28T09:24:59+05:30")
    assert old.blocked is True
    assert old.reason == REASON_LOOKBACK_EXCEEDED


def test_future_candle_high_low_close_access_is_rejected_until_candle_is_complete():
    clock = build_replay_clock(
        session_start=SESSION_START,
        session_end=SESSION_END,
        current_timestamp="2026-05-28T09:31:00+05:30",
        lookback_seconds=900,
    )

    decision = clock.candle_field_access(
        candle_start="2026-05-28T09:30:00+05:30",
        candle_end="2026-05-28T09:35:00+05:30",
        field_name="high",
    )
    assert decision.blocked is True
    assert decision.reason == REASON_CANDLE_FIELD_IN_FUTURE

    open_decision = clock.candle_field_access(
        candle_start="2026-05-28T09:30:00+05:30",
        candle_end="2026-05-28T09:35:00+05:30",
        field_name="open",
    )
    assert open_decision.allowed is True

    complete_clock = clock.advance_to("2026-05-28T09:35:00+05:30")
    assert complete_clock.candle_field_access(
        candle_start="2026-05-28T09:30:00+05:30",
        candle_end="2026-05-28T09:35:00+05:30",
        field_name="close",
    ).allowed is True


def test_full_session_aggregates_are_unavailable_before_session_completion():
    clock = build_replay_clock(
        session_start=SESSION_START,
        session_end=SESSION_END,
        current_timestamp="2026-05-28T15:29:59+05:30",
        lookback_seconds=900,
    )

    blocked = clock.full_session_aggregate_access("day_high")
    assert blocked.blocked is True
    assert blocked.reason == REASON_FULL_SESSION_AGGREGATE_UNAVAILABLE

    completed = clock.advance_to(SESSION_END)
    assert completed.full_session_aggregate_access("day_high").allowed is True


def test_invalid_non_monotonic_replay_data_fails_closed():
    with pytest.raises(ReplayClockContractError, match=REASON_NON_MONOTONIC_REPLAY_DATA):
        validate_monotonic_replay_timestamps(
            [
                "2026-05-28T09:15:00+05:30",
                "2026-05-28T09:16:00+05:30",
                "2026-05-28T09:15:59+05:30",
            ],
            session_start=SESSION_START,
            session_end=SESSION_END,
        )


def test_visible_snapshots_filters_without_exposing_future_data():
    clock = build_replay_clock(
        session_start=SESSION_START,
        session_end=SESSION_END,
        current_timestamp="2026-05-28T09:20:00+05:30",
        lookback_seconds=600,
    )
    snapshots = [
        {"timestamp": "2026-05-28T09:16:00+05:30", "symbol": "NIFTY"},
        {"timestamp": "2026-05-28T09:20:00+05:30", "symbol": "BANKNIFTY"},
        {"timestamp": "2026-05-28T09:20:01+05:30", "symbol": "SENSEX"},
    ]

    result = visible_snapshots(clock, snapshots)

    assert [snapshot["symbol"] for snapshot in result] == ["NIFTY", "BANKNIFTY"]


def test_invalid_session_window_and_naive_timestamps_fail_closed():
    with pytest.raises(ReplayClockContractError):
        build_replay_clock(session_start=SESSION_START, session_end=SESSION_START)

    with pytest.raises(ReplayClockContractError):
        build_replay_clock(session_start="2026-05-28T09:15:00", session_end=SESSION_END)
