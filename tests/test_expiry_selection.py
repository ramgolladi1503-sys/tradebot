from datetime import date

from config import config as cfg
import core.market_calendar as market_calendar
from core.option_chain import _choose_expiry


def test_choose_expiry_prefers_nearest_available_non_holiday(monkeypatch):
    monkeypatch.setattr(market_calendar, "IN_HOLIDAYS", {date(2030, 1, 28)})
    available = [date(2030, 1, 30), date(2030, 2, 4), date(2030, 1, 28)]
    chosen = _choose_expiry(available, preferred_expiry=date(2030, 2, 4))
    assert chosen == date(2030, 1, 30)


def test_nearest_expiry_skips_nse_fno_exchange_holiday():
    chosen = market_calendar.choose_nearest_available_expiry(
        [date(2026, 3, 3), date(2026, 3, 4)], today=date(2026, 3, 3)
    )
    assert chosen == date(2026, 3, 4)


def test_nearest_expiry_returns_none_when_all_exchange_dates_are_closed():
    chosen = market_calendar.choose_nearest_available_expiry(
        [date(2026, 3, 3)], today=date(2026, 3, 3)
    )
    assert chosen is None


def test_exchange_calendar_does_not_inherit_non_exchange_india_holiday(monkeypatch):
    # The general India calendar marks March 4 as Holi, but NSE F&O's
    # authoritative 2026 circular lists March 3 as the closure.
    monkeypatch.setattr(market_calendar, "IN_HOLIDAYS", {date(2026, 3, 4)})
    assert not market_calendar._is_nse_fno_holiday(date(2026, 3, 4))


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
