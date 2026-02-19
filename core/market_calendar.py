from datetime import date, datetime, timedelta

from config import config as cfg
from core.time_utils import now_ist

try:
    import holidays

    IN_HOLIDAYS = holidays.India(years=now_ist().date().year)
except Exception:
    IN_HOLIDAYS = set()


def _coerce_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.fromisoformat(text).date()
    except Exception:
        return None


def _default_weekly_expiry_weekday(symbol: str | None) -> int:
    # NSE index weeklies: Tuesday, BSE SENSEX weekly: Thursday.
    sym = str(symbol or "NIFTY").upper()
    return 3 if sym == "SENSEX" else 1

def _weekly_expiry_weekday(symbol: str | None):
    sym = (symbol or "NIFTY").upper()
    exp_map = getattr(cfg, "EXPIRY_WEEKDAY_BY_SYMBOL", {}) or {}
    try:
        if exp_map:
            if sym in exp_map:
                return int(exp_map[sym])
            return int(_default_weekly_expiry_weekday(sym))
    except Exception:
        pass
    return int(_default_weekly_expiry_weekday(sym))


def choose_nearest_available_expiry(available_expiries, today: date | None = None):
    """
    Prefer nearest non-holiday expiry >= today from exchange-provided expiries.
    """
    normalized = sorted({d for d in (_coerce_date(x) for x in (available_expiries or [])) if d is not None})
    if not normalized:
        return None
    ref = today or now_ist().date()
    non_holiday_future = [d for d in normalized if d >= ref and d not in IN_HOLIDAYS]
    if non_holiday_future:
        return non_holiday_future[0]
    non_holiday_any = [d for d in normalized if d not in IN_HOLIDAYS]
    if non_holiday_any:
        return non_holiday_any[0]
    return normalized[0]

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
