from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.market_calendar import market_open


def test_market_open_boundary_ist():
    ist = ZoneInfo("Asia/Kolkata")
    before_open = datetime(2026, 3, 2, 9, 14, tzinfo=ist)
    at_open = datetime(2026, 3, 2, 9, 15, tzinfo=ist)
    assert market_open(now=before_open) is False
    assert market_open(now=at_open) is True
