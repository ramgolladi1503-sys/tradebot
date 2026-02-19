from datetime import date

from config import config as cfg
import core.market_calendar as market_calendar
from core.option_chain import _choose_expiry


def test_choose_expiry_prefers_nearest_available_non_holiday(monkeypatch):
    monkeypatch.setattr(market_calendar, "IN_HOLIDAYS", {date(2030, 1, 28)})
    available = [date(2030, 1, 30), date(2030, 2, 4), date(2030, 1, 28)]
    chosen = _choose_expiry(available, preferred_expiry=date(2030, 2, 4))
    assert chosen == date(2030, 1, 30)


def test_weekday_fallback_mapping_uses_tuesday_for_nse_and_thursday_for_sensex(monkeypatch):
    monkeypatch.setattr(market_calendar, "IN_HOLIDAYS", set())
    monkeypatch.setattr(cfg, "EXPIRY_WEEKDAY_BY_SYMBOL", {}, raising=False)
    monkeypatch.setattr(cfg, "EXPIRY_DAY", 4, raising=False)  # legacy value should not control fallback

    start = date(2026, 2, 18)  # Wednesday
    nifty_next = market_calendar.next_expiry_after(start, symbol="NIFTY")
    banknifty_next = market_calendar.next_expiry_after(start, symbol="BANKNIFTY")
    sensex_next = market_calendar.next_expiry_after(start, symbol="SENSEX")

    assert nifty_next.weekday() == 1
    assert banknifty_next.weekday() == 1
    assert sensex_next.weekday() == 3
