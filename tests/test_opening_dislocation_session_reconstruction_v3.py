from __future__ import annotations

from datetime import date

from research.opening_dislocation_reversal.fresh_epoch_reconciliation_v3 import (
    STANDARD_MINUTE_COUNT,
    classify_calendar_date,
    classify_session,
    expected_minute_grid,
)


def test_expected_calendar_distinguishes_weekend_holiday_and_regular_session():
    assert classify_calendar_date(date(2022, 1, 1)) == "WEEKEND"
    assert classify_calendar_date(date(2022, 1, 26)) == "OFFICIAL_HOLIDAY"
    assert classify_calendar_date(date(2022, 10, 24)) == "NONSTANDARD_SPECIAL_SESSION"
    assert classify_calendar_date(date(2022, 1, 3)) == "EXPECTED_REGULAR_SESSION"


def test_375_row_fingerprint_boundaries_are_start_labelled():
    grid = expected_minute_grid("2022-01-03")
    assert len(grid) == STANDARD_MINUTE_COUNT
    assert grid[0].strftime("%H:%M") == "09:15"
    assert grid[-1].strftime("%H:%M") == "15:29"
    assert "15:30" not in {x.strftime("%H:%M") for x in grid}


def test_missing_extra_duplicate_and_complete_classifications():
    assert classify_session(375, 0, 0) == "COMPLETE_STANDARD_SESSION"
    assert classify_session(374, 0, 0) == "INCOMPLETE_MISSING_MINUTES"
    assert classify_session(376, 0, 0) == "EXTRA_REGULAR_SESSION_MINUTES"
    assert classify_session(375, 1, 0) == "DUPLICATE_TIMESTAMPS"
    assert classify_session(375, 0, 1) == "INVALID_OHLC"
