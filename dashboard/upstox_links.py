from __future__ import annotations

import urllib.parse
from datetime import datetime

# Best-effort Upstox deep link pattern. If it breaks, search fallback still works.
UPSTOX_CONTRACT_URL = "https://pro.upstox.com/instruments/{instrument_key}"
UPSTOX_SEARCH_URL = "https://pro.upstox.com/search?query={query}"
_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def build_upstox_contract_url(upstox_instrument_key: str) -> str:
    if not upstox_instrument_key:
        return ""
    return UPSTOX_CONTRACT_URL.format(instrument_key=urllib.parse.quote(str(upstox_instrument_key)))


def _format_expiry(expiry: str) -> str:
    text = str(expiry or "").strip()
    if not text:
        return ""
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        dt = datetime.fromisoformat(text).date()
        return f"{dt.day:02d} {_MONTHS[dt.month - 1]}"
    except Exception:
        return text.replace("-", " ").strip()


def build_upstox_search_query(row: dict) -> str:
    if not isinstance(row, dict):
        return ""
    underlying = str(row.get("underlying") or row.get("symbol") or "").upper()
    expiry = _format_expiry(row.get("expiry_date") or row.get("expiry"))
    strike = str(row.get("strike") or "").strip()
    opt_type = str(row.get("option_type") or row.get("type") or row.get("right") or "").upper()
    if opt_type in ("CALL", "CE"):
        opt_type = "CE"
    elif opt_type in ("PUT", "PE"):
        opt_type = "PE"
    parts = [p for p in [underlying, expiry, strike, opt_type] if p]
    return " ".join(parts)


def build_upstox_search_url(query: str) -> str:
    if not query:
        return ""
    return UPSTOX_SEARCH_URL.format(query=urllib.parse.quote(query))
