from __future__ import annotations

from datetime import datetime


IMPORTANT_EVENTS = {
    "RBI",
    "FOMC",
    "CPI",
    "BUDGET",
}


def is_event_window(event_calendar: list[dict], now: datetime) -> bool:
    for event in event_calendar:
        if event.get("name") in IMPORTANT_EVENTS:
            start = event.get("start")
            end = event.get("end")
            if start and end and start <= now <= end:
                return True
    return False


def event_risk_multiplier(event_calendar: list[dict], now: datetime) -> float:
    if is_event_window(event_calendar, now):
        return 0.5
    return 1.0
