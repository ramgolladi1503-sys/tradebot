# Migration note:
# Introduces deterministic option tradingsymbol generation for fixtures and replay validation.

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from config import config as cfg

MONTH_CODES = {
    1: "JAN",
    2: "FEB",
    3: "MAR",
    4: "APR",
    5: "MAY",
    6: "JUN",
    7: "JUL",
    8: "AUG",
    9: "SEP",
    10: "OCT",
    11: "NOV",
    12: "DEC",
}


@dataclass(frozen=True)
class TradingsymbolBuildResult:
    tradingsymbol: str | None
    reason: str
    expiry_date: date | None = None


def _coerce_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text or text.upper() in {"NONE", "NA", "N/A", "NAN"}:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.fromisoformat(text).date()
    except Exception:
        return None


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    if month == 12:
        first_next = date(year + 1, 1, 1)
    else:
        first_next = date(year, month + 1, 1)
    cursor = first_next - timedelta(days=1)
    while cursor.weekday() != weekday:
        cursor -= timedelta(days=1)
    return cursor


def is_monthly_expiry(expiry: date, symbol: str | None = None) -> bool:
    weekly_day_map = getattr(cfg, "OPTION_TS_MONTHLY_WEEKDAY_BY_SYMBOL", {}) or {}
    default_weekday = int(getattr(cfg, "OPTION_TS_MONTHLY_WEEKDAY", 3))
    weekday = int(weekly_day_map.get(str(symbol or "").upper(), default_weekday))
    last_weekday = _last_weekday_of_month(expiry.year, expiry.month, weekday)
    return expiry == last_weekday


def build_option_tradingsymbol(
    symbol: str | None,
    expiry,
    strike,
    right: str | None,
    *,
    weekly_with_day: bool | None = None,
    monthly_with_day: bool | None = None,
) -> TradingsymbolBuildResult:
    if not symbol:
        return TradingsymbolBuildResult(None, "missing_symbol")
    expiry_date = _coerce_date(expiry)
    if expiry_date is None:
        return TradingsymbolBuildResult(None, "invalid_expiry")
    if strike is None:
        return TradingsymbolBuildResult(None, "missing_strike", expiry_date=expiry_date)
    right_text = str(right or "").strip().upper()
    if right_text not in {"CE", "PE"}:
        return TradingsymbolBuildResult(None, "invalid_right", expiry_date=expiry_date)
    try:
        strike_val = int(float(strike))
    except Exception:
        return TradingsymbolBuildResult(None, "invalid_strike", expiry_date=expiry_date)

    if weekly_with_day is None:
        weekly_with_day = bool(getattr(cfg, "OPTION_TS_WEEKLY_INCLUDE_DAY", True))
    if monthly_with_day is None:
        monthly_with_day = bool(getattr(cfg, "OPTION_TS_MONTHLY_INCLUDE_DAY", False))

    sym = str(symbol).upper()
    yy = expiry_date.strftime("%y")
    mon = MONTH_CODES.get(expiry_date.month, expiry_date.strftime("%b").upper())
    use_day = monthly_with_day if is_monthly_expiry(expiry_date, sym) else weekly_with_day
    day = f"{expiry_date.day:02d}" if use_day else ""

    tradingsymbol = f"{sym}{yy}{mon}{day}{strike_val}{right_text}"
    return TradingsymbolBuildResult(tradingsymbol, "ok", expiry_date=expiry_date)

