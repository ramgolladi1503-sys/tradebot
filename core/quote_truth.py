from __future__ import annotations

from typing import Any

from config import config as cfg


_PRESERVE_STATUSES = {
    "DISPLAYABLE",
    "NON_EXECUTABLE",
    "OFFHOURS_SYNTHETIC",
    "PRICE_MISMATCH",
    "REST_FALLBACK",
}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _text(value: Any) -> str:
    if value in (None, "", "None"):
        return ""
    return str(value).strip().upper()


def resolve_quote_validation_status(
    *,
    existing_status: Any = None,
    current_ltp: Any = None,
    quote_age_sec: Any = None,
    best_bid: Any = None,
    best_ask: Any = None,
    max_quote_age_sec: Any = None,
) -> str:
    existing = _text(existing_status)
    current_ltp_f = _safe_float(current_ltp)
    age_f = _safe_float(quote_age_sec)
    best_bid_f = _safe_float(best_bid)
    best_ask_f = _safe_float(best_ask)
    max_age = _safe_float(max_quote_age_sec)
    if max_age is None or max_age <= 0:
        max_age = _safe_float(getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8.0)) or 8.0

    if existing in _PRESERVE_STATUSES:
        return existing

    if current_ltp_f is None:
        return "NO_LIVE_OPTION_FEED"

    if age_f is not None and age_f > float(max_age):
        return "STALE_OPTION_LTP"

    if best_bid_f is not None and best_ask_f is not None and best_ask_f >= best_bid_f:
        return "OK"

    return "UNKNOWN"
