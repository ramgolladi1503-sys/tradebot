from datetime import date

from core.instrument_symbols import build_option_tradingsymbol


def test_tradingsymbol_monthly_no_day():
    result = build_option_tradingsymbol("NIFTY", date(2026, 2, 26), 25700, "CE")
    assert result.tradingsymbol == "NIFTY26FEB25700CE"


def test_tradingsymbol_weekly_with_day():
    result = build_option_tradingsymbol("NIFTY", date(2026, 2, 19), 25100, "CE")
    assert result.tradingsymbol == "NIFTY26FEB1925100CE"

