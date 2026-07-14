from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.session_bar_history import (
    SessionBarHistoryError,
    build_session_bar_history_state,
    session_history_bound,
)


IST = ZoneInfo("Asia/Kolkata")


def _bar(ts: datetime, o: float, h: float, low: float, c: float, volume: float = 100.0) -> dict:
    return {
        "ts": ts,
        "open": o,
        "high": h,
        "low": low,
        "close": c,
        "volume": volume,
    }


def test_completed_history_excludes_incomplete_current_bar_and_derives_session_state() -> None:
    base = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    bars = [
        _bar(base + timedelta(minutes=0), 100.0, 101.0, 99.0, 100.5),
        _bar(base + timedelta(minutes=1), 100.5, 102.0, 100.0, 101.5),
        _bar(base + timedelta(minutes=2), 101.5, 103.0, 101.0, 102.5),
    ]

    state = build_session_bar_history_state(
        symbol="NIFTY",
        bars=bars,
        cutoff_timestamp=base + timedelta(minutes=2, seconds=30),
        segment="NSE_FNO",
        source="unit_test",
    )

    assert state.completed_bar_count == 2
    assert [bar.bar_start_timestamp for bar in state.completed_bar_history] == [
        (base + timedelta(minutes=0)).isoformat(),
        (base + timedelta(minutes=1)).isoformat(),
    ]
    assert state.open_price == 100.0
    assert state.day_high == 102.0
    assert state.day_low == 99.0
    assert state.previous_completed_close == 100.5
    assert state.latest_completed_timestamp == (base + timedelta(minutes=2)).isoformat()
    assert state.partial_session is True


def test_history_is_defensively_copied_and_hash_stable() -> None:
    base = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    bars = [
        _bar(base + timedelta(minutes=0), 100.0, 101.0, 99.0, 100.5),
        _bar(base + timedelta(minutes=1), 100.5, 102.0, 100.0, 101.5),
    ]

    state_a = build_session_bar_history_state(
        symbol="NIFTY",
        bars=bars,
        cutoff_timestamp=base + timedelta(minutes=3),
        segment="NSE_FNO",
        source="unit_test",
    )
    first_hash = state_a.history_hash
    bars[0]["high"] = 999.0
    state_b = build_session_bar_history_state(
        symbol="NIFTY",
        bars=[
            _bar(base + timedelta(minutes=0), 100.0, 101.0, 99.0, 100.5),
            _bar(base + timedelta(minutes=1), 100.5, 102.0, 100.0, 101.5),
        ],
        cutoff_timestamp=base + timedelta(minutes=3),
        segment="NSE_FNO",
        source="unit_test",
    )

    assert state_a.day_high == 102.0
    assert state_a.history_hash == first_hash
    assert state_a.history_hash == state_b.history_hash


def test_duplicate_and_out_of_order_bars_fail_deterministically() -> None:
    base = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    duplicate = [
        _bar(base, 100.0, 101.0, 99.0, 100.5),
        _bar(base, 100.5, 102.0, 100.0, 101.5),
    ]
    out_of_order = [
        _bar(base + timedelta(minutes=1), 100.5, 102.0, 100.0, 101.5),
        _bar(base, 100.0, 101.0, 99.0, 100.5),
    ]

    with pytest.raises(SessionBarHistoryError, match="duplicate_bar_timestamp"):
        build_session_bar_history_state(
            symbol="NIFTY",
            bars=duplicate,
            cutoff_timestamp=base + timedelta(minutes=3),
            segment="NSE_FNO",
            source="unit_test",
        )

    with pytest.raises(SessionBarHistoryError, match="out_of_order_bar"):
        build_session_bar_history_state(
            symbol="NIFTY",
            bars=out_of_order,
            cutoff_timestamp=base + timedelta(minutes=3),
            segment="NSE_FNO",
            source="unit_test",
        )


def test_zero_volume_history_is_not_reported_as_truthful_volume() -> None:
    base = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    bars = [
        _bar(base + timedelta(minutes=0), 100.0, 101.0, 99.0, 100.5, volume=0.0),
        _bar(base + timedelta(minutes=1), 100.5, 102.0, 100.0, 101.5, volume=0.0),
    ]

    state = build_session_bar_history_state(
        symbol="NIFTY",
        bars=bars,
        cutoff_timestamp=base + timedelta(minutes=3),
        segment="NSE_FNO",
        source="unit_test",
    )

    assert all(bar.volume is None for bar in state.completed_bar_history)


def test_session_reset_requires_new_session_history() -> None:
    day_one = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    day_two = datetime(2026, 7, 15, 9, 15, tzinfo=IST)
    bars = [
        _bar(day_one + timedelta(minutes=0), 100.0, 101.0, 99.0, 100.5),
        _bar(day_one + timedelta(minutes=1), 100.5, 102.0, 100.0, 101.5),
        _bar(day_two + timedelta(minutes=0), 200.0, 201.0, 199.0, 200.5),
    ]

    state = build_session_bar_history_state(
        symbol="NIFTY",
        bars=bars,
        cutoff_timestamp=day_two + timedelta(minutes=2),
        segment="NSE_FNO",
        source="unit_test",
    )

    assert state.session_date == "2026-07-15"
    assert state.completed_bar_count == 1
    assert state.open_price == 200.0
    assert state.day_high == 201.0
    assert state.day_low == 199.0
    assert state.previous_completed_close is None


def test_history_bound_matches_regular_one_minute_session() -> None:
    assert session_history_bound(segment="NSE_FNO") == 375
