from datetime import date, timedelta
import holidays
from config import config as cfg
from core.time_utils import now_ist

IN_HOLIDAYS = holidays.India(years=now_ist().date().year)

def _weekly_expiry_weekday(symbol: str | None):
    sym = (symbol or "NIFTY").upper()
    exp_map = getattr(cfg, "EXPIRY_WEEKDAY_BY_SYMBOL", {})
    try:
        return int(exp_map.get(sym, 3))
    except Exception:
        return 3

def next_expiry(symbol: str | None = None):
    """
    Next weekly expiry for a symbol (per config), skipping holidays.
    """
    today = now_ist().date()
    weekday = _weekly_expiry_weekday(symbol)
    for i in range(1, 15):
        candidate = today + timedelta(days=i)
        if candidate.weekday() == weekday and candidate not in IN_HOLIDAYS:
            return candidate
    return None

def next_monthly_expiry():
    """
    Last Thursday of current or next month, skipping holidays.
    """
    today = now_ist().date()
    year = today.year
    month = today.month
    for _ in range(2):
        # find last Thursday
        last_day = date(year, month, 28)
        while True:
            try:
                last_day = date(year, month, last_day.day + 1)
            except Exception:
                break
        d = last_day
        while d.weekday() != 3:  # Thursday
            d -= timedelta(days=1)
        if d >= today and d not in IN_HOLIDAYS:
            return d
        # move to next month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return None

def next_expiry_by_type(expiry_type="WEEKLY", symbol: str | None = None):
    if str(expiry_type).upper() == "MONTHLY":
        return next_monthly_expiry()
    return next_expiry(symbol=symbol)

def next_expiry_after(start_date, expiry_type="WEEKLY", symbol: str | None = None):
    """
    Next expiry after given date, based on expiry type.
    """
    if str(expiry_type).upper() == "MONTHLY":
        # move to next month and get monthly expiry
        month = start_date.month + 1
        year = start_date.year
        if month > 12:
            month = 1
            year += 1
        target_month = month
        target_year = year
        # compute last Thursday of target month
        last_day = date(target_year, target_month, 28)
        while True:
            try:
                last_day = date(target_year, target_month, last_day.day + 1)
            except Exception:
                break
        d = last_day
        while d.weekday() != 3:
            d -= timedelta(days=1)
        return d if d not in IN_HOLIDAYS else None
    weekday = _weekly_expiry_weekday(symbol)
    for i in range(1, 15):
        candidate = start_date + timedelta(days=i)
        if candidate.weekday() == weekday and candidate not in IN_HOLIDAYS:
            return candidate
    return None
