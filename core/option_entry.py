"""Option entry validation based on live LTP.

Migration note:
Ensures suggested entry is derived from live option LTP and blocks stale prices.
"""

from __future__ import annotations

from typing import Any

from config import config as cfg
from core.time_utils import now_utc_epoch, compute_age_sec


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def validate_live_entry(
    *,
    signal_price: float | None,
    current_ltp: float | None,
    ltp_ts_epoch: float | None,
    now_epoch: float | None = None,
    mismatch_pct: float | None = None,
    max_age_sec: float | None = None,
) -> dict[str, Any]:
    now_epoch = float(now_epoch if now_epoch is not None else now_utc_epoch())
    mismatch_pct = float(mismatch_pct if mismatch_pct is not None else getattr(cfg, "OPTION_ENTRY_MISMATCH_PCT", 0.03))
    max_age_sec = float(max_age_sec if max_age_sec is not None else getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0))

    out: dict[str, Any] = {
        "signal_price": signal_price,
        "current_ltp": current_ltp,
        "suggested_entry": None,
        "entry_status": None,
        "price_age_sec": None,
        "valid": False,
    }
    if current_ltp is None or ltp_ts_epoch is None:
        out["entry_status"] = "NO_LIVE_OPTION_FEED"
        return out
    age_sec = compute_age_sec(float(ltp_ts_epoch), now_epoch)
    out["price_age_sec"] = age_sec
    if age_sec is None or age_sec > max_age_sec:
        out["entry_status"] = "STALE_OPTION_LTP"
        return out
    sig_val = _to_float(signal_price)
    ltp_val = _to_float(current_ltp)
    if ltp_val is None or ltp_val <= 0:
        out["entry_status"] = "INVALID_LTP"
        return out
    if sig_val is not None:
        diff = abs(sig_val - ltp_val) / ltp_val
        if diff > mismatch_pct:
            out["entry_status"] = "STALE_PRICE"
            return out
    out["suggested_entry"] = ltp_val
    out["entry_status"] = "OK"
    out["valid"] = True
    return out

