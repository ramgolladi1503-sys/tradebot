"""Expiry Calendar Resolver.

Dynamically identifies weekly and monthly expiry sessions across NSE and BSE:
- NIFTY 50:
    * Pre-2025-09-01 era: Thursday (falling back to Wednesday if Thursday is a trading holiday).
    * Post-2025-09-01 era: Tuesday (falling back to Monday if Tuesday is a trading holiday).
- SENSEX:
    * Current era: Thursday (falling back to Wednesday if Thursday is a trading holiday).
- BANKNIFTY:
    * Wednesday (falling back to Tuesday if Wednesday is a trading holiday).

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set


@dataclass(slots=True, frozen=True)
class ExpiryClassification:
    date: datetime.date
    day_name: str
    is_nifty_expiry: bool
    is_sensex_expiry: bool
    is_banknifty_expiry: bool
    fallback_from_holiday: bool
    active_expiry_index: Optional[str]


class ExpiryCalendarResolver:
    """Institutional Expiry Calendar Resolver adhering strictly to SEBI & Exchange circulars."""

    def __init__(self, known_holidays: Optional[Set[datetime.date]] = None):
        # Known Indian Exchange Trading Holidays (2024-2026)
        self.known_holidays = known_holidays or {
            # 2024 Holidays
            datetime.date(2024, 1, 26), datetime.date(2024, 3, 8), datetime.date(2024, 3, 25),
            datetime.date(2024, 3, 29), datetime.date(2024, 4, 11), datetime.date(2024, 4, 17),
            datetime.date(2024, 5, 1), datetime.date(2024, 5, 20), datetime.date(2024, 6, 17),
            datetime.date(2024, 7, 17), datetime.date(2024, 8, 15), datetime.date(2024, 10, 2),
            datetime.date(2024, 11, 1), datetime.date(2024, 11, 15), datetime.date(2024, 12, 25),
            # 2025 Holidays
            datetime.date(2025, 2, 26), datetime.date(2025, 3, 14), datetime.date(2025, 3, 31),
            datetime.date(2025, 4, 10), datetime.date(2025, 4, 14), datetime.date(2025, 4, 18),
            datetime.date(2025, 5, 1), datetime.date(2025, 8, 15), datetime.date(2025, 8, 27),
            datetime.date(2025, 10, 2), datetime.date(2025, 10, 21), datetime.date(2025, 10, 22),
            datetime.date(2025, 11, 5), datetime.date(2025, 12, 25),
            # 2026 Holidays
            datetime.date(2026, 1, 26), datetime.date(2026, 3, 3), datetime.date(2026, 3, 20),
            datetime.date(2026, 3, 31), datetime.date(2026, 4, 3), datetime.date(2026, 4, 14),
            datetime.date(2026, 5, 1), datetime.date(2026, 10, 2), datetime.date(2026, 10, 20),
            datetime.date(2026, 11, 10), datetime.date(2026, 11, 24), datetime.date(2026, 12, 25),
        }

    def is_holiday(self, d: datetime.date) -> bool:
        return d in self.known_holidays or d.weekday() >= 5  # Sat / Sun

    def classify_session(
        self,
        target_date: datetime.date,
        calendar_sessions: Optional[Sequence[datetime.date]] = None,
    ) -> ExpiryClassification:
        dow = target_date.strftime("%A")
        is_post_sept_2025 = target_date >= datetime.date(2025, 9, 1)

        # 1. NIFTY Expiry Check
        is_nifty = False
        nifty_fallback = False

        if not is_post_sept_2025:
            # Old Era: Thursday
            if dow == "Thursday":
                is_nifty = True
            elif dow == "Wednesday":
                # Check if Thursday is holiday
                thu = target_date + datetime.timedelta(days=1)
                if self.is_holiday(thu):
                    is_nifty = True
                    nifty_fallback = True
        else:
            # New Era: Tuesday (or Monday if Tuesday is holiday)
            if dow == "Tuesday":
                is_nifty = True
            elif dow == "Monday":
                tue = target_date + datetime.timedelta(days=1)
                if self.is_holiday(tue):
                    is_nifty = True
                    nifty_fallback = True

        # 2. SENSEX Expiry Check (Thursday or Wednesday if Thursday is holiday)
        is_sensex = False
        sensex_fallback = False
        if dow == "Thursday":
            is_sensex = True
        elif dow == "Wednesday":
            thu = target_date + datetime.timedelta(days=1)
            if self.is_holiday(thu):
                is_sensex = True
                sensex_fallback = True

        # 3. BANKNIFTY Expiry Check (Wednesday or Tuesday if Wednesday is holiday)
        is_banknifty = False
        banknifty_fallback = False
        if dow == "Wednesday":
            is_banknifty = True
        elif dow == "Tuesday":
            wed = target_date + datetime.timedelta(days=1)
            if self.is_holiday(wed):
                is_banknifty = True
                banknifty_fallback = True

        active_idx = None
        if is_nifty:
            active_idx = "NIFTY"
        elif is_sensex:
            active_idx = "SENSEX"
        elif is_banknifty:
            active_idx = "BANKNIFTY"

        return ExpiryClassification(
            date=target_date,
            day_name=dow,
            is_nifty_expiry=is_nifty,
            is_sensex_expiry=is_sensex,
            is_banknifty_expiry=is_banknifty,
            fallback_from_holiday=nifty_fallback or sensex_fallback or banknifty_fallback,
            active_expiry_index=active_idx,
        )
