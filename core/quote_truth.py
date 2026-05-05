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


def _quote_band_tolerance_pct() -> float:
    tol = _safe_float(getattr(cfg, "OPTION_LAST_OUTSIDE_BAND_PCT", 0.01))
    if tol is None or tol < 0:
        return 0.01
    return float(tol)


def quote_bundle_is_consistent(
    *,
    current_ltp: Any = None,
    best_bid: Any = None,
    best_ask: Any = None,
) -> bool:
    score = quote_consistency_score(
        current_ltp=current_ltp,
        best_bid=best_bid,
        best_ask=best_ask,
    )
    if score is None:
        return True
    return float(score) > 0.0


def quote_consistency_score(
    *,
    current_ltp: Any = None,
    best_bid: Any = None,
    best_ask: Any = None,
) -> float | None:
    current_ltp_f = _safe_float(current_ltp)
    best_bid_f = _safe_float(best_bid)
    best_ask_f = _safe_float(best_ask)
    if current_ltp_f is None or best_bid_f is None or best_ask_f is None:
        return None
    if best_bid_f <= 0 or best_ask_f <= 0 or best_ask_f < best_bid_f:
        return 0.0
    if float(best_bid_f) <= float(current_ltp_f) <= float(best_ask_f):
        return 1.0
    spread = max(0.0, float(best_ask_f) - float(best_bid_f))
    mid = (float(best_bid_f) + float(best_ask_f)) / 2.0
    tolerance = max(spread, abs(mid) * _quote_band_tolerance_pct())
    if tolerance <= 0.0:
        return 0.0
    if float(current_ltp_f) < float(best_bid_f):
        excess = float(best_bid_f) - float(current_ltp_f)
    else:
        excess = float(current_ltp_f) - float(best_ask_f)
    return max(0.0, min(1.0, round(1.0 - (excess / tolerance), 6)))


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

    if not quote_bundle_is_consistent(
        current_ltp=current_ltp_f,
        best_bid=best_bid_f,
        best_ask=best_ask_f,
    ):
        return "PRICE_MISMATCH"

    if age_f is not None and age_f > float(max_age):
        return "STALE_OPTION_LTP"

    if best_bid_f is not None and best_ask_f is not None and best_ask_f >= best_bid_f:
        return "OK"

    return "OK"
