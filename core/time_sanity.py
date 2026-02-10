from __future__ import annotations

from datetime import datetime
from typing import Any

from config import config as cfg
from core.time_utils import now_utc_epoch


def to_epoch(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "timestamp"):
        try:
            return float(value.timestamp())
        except Exception:
            return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")
        return float(datetime.fromisoformat(text).timestamp())
    except Exception:
        return None


def check_market_data_time_sanity(
    *,
    ltp_ts_epoch: float | None,
    candle_ts_epoch: float | None,
    market_open: bool,
    require_live_quotes: bool,
    max_ltp_age_sec: float | None = None,
    max_candle_age_sec: float | None = None,
    now_epoch: float | None = None,
) -> dict:
    now_ts = float(now_epoch if now_epoch is not None else now_utc_epoch())
    ltp_age_sec = None if ltp_ts_epoch is None else max(0.0, now_ts - float(ltp_ts_epoch))
    candle_age_sec = None if candle_ts_epoch is None else max(0.0, now_ts - float(candle_ts_epoch))

    reasons: list[str] = []
    if market_open and require_live_quotes:
        ltp_limit = float(max_ltp_age_sec if max_ltp_age_sec is not None else getattr(cfg, "MAX_LTP_AGE_SEC", 8))
        candle_limit = float(max_candle_age_sec if max_candle_age_sec is not None else getattr(cfg, "MAX_CANDLE_AGE_SEC", 120))
        if ltp_age_sec is None or ltp_age_sec > ltp_limit:
            reasons.append("LTP_STALE")
        if candle_age_sec is None or candle_age_sec > candle_limit:
            reasons.append("CANDLE_STALE")

    return {
        "ok": len(reasons) == 0,
        "reasons": reasons,
        "ltp_age_sec": ltp_age_sec,
        "candle_age_sec": candle_age_sec,
        "ltp_ts_epoch": ltp_ts_epoch,
        "candle_ts_epoch": candle_ts_epoch,
        "market_open": bool(market_open),
        "require_live_quotes": bool(require_live_quotes),
    }
