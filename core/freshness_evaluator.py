from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import logging
from typing import Any

from config import config as cfg
from core.time_utils import now_utc_epoch

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FreshnessDecision:
    symbol: str
    instrument_token: int | None
    decision_type: str
    market_open: bool
    now_epoch: float
    quote_epoch: float | None
    candle_epoch: float | None
    selected_epoch: float | None
    selected_source: str
    quote_age_sec: float | None
    candle_age_sec: float | None
    selected_age_sec: float | None
    threshold_sec: float
    blocker: bool
    reason: str
    trade_id: str | None
    ts_iso: str

    @property
    def fresh(self) -> bool:
        return not bool(self.blocker)

    @property
    def evaluated_at_epoch(self) -> float:
        return float(self.now_epoch)

    @property
    def freshness_reason(self) -> str:
        return str(self.reason)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["fresh"] = self.fresh
        payload["evaluated_at_epoch"] = self.evaluated_at_epoch
        payload["freshness_reason"] = self.freshness_reason
        return payload


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _safe_positive_float(value: Any) -> float | None:
    out = _safe_float(value)
    if out is None:
        return None
    return out if out > 0 else None


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, "", "None"):
            return None
        out = int(value)
        return out if out > 0 else None
    except Exception:
        return None


def _iso_utc(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()


def _age_sec(epoch: float | None, now_epoch: float) -> float | None:
    if epoch is None:
        return None
    return float(now_epoch) - float(epoch)


def _non_negative_age(value: float | None) -> float | None:
    if value is None:
        return None
    return value if value >= 0.0 else None


def _future_skew_sec() -> float:
    try:
        return max(0.0, float(getattr(cfg, "FRESHNESS_MAX_FUTURE_SKEW_SEC", 1.0)))
    except Exception:
        return 1.0


def evaluate_quote_freshness(
    *,
    symbol: str,
    instrument_token: Any,
    quote_epoch: Any,
    candle_epoch: Any,
    threshold_sec: Any,
    market_open: bool,
    trade_id: str | None = None,
    allow_candle_fallback: bool = False,
    decision_type: str = "option_quote",
    now_epoch: float | None = None,
) -> FreshnessDecision:
    now_ts = float(now_epoch if now_epoch is not None else now_utc_epoch())
    quote_ts = _safe_positive_float(quote_epoch)
    candle_ts = _safe_positive_float(candle_epoch)
    threshold = max(0.0, float(_safe_float(threshold_sec) or 0.0))
    skew_limit = _future_skew_sec()

    quote_age_raw = _age_sec(quote_ts, now_ts)
    candle_age_raw = _age_sec(candle_ts, now_ts)

    selected_epoch = quote_ts
    selected_source = "quote"
    selected_age_raw = quote_age_raw
    blocker = False
    reason = "quote_missing"

    if quote_ts is None:
        selected_epoch = None
        selected_source = "none"
        selected_age_raw = None
        if allow_candle_fallback and candle_ts is not None:
            selected_epoch = candle_ts
            selected_source = "candle"
            selected_age_raw = candle_age_raw
            if candle_age_raw is not None and candle_age_raw < (-1.0 * skew_limit):
                blocker = True
                reason = "quote_in_future_clock_skew"
            elif not bool(market_open):
                blocker = False
                reason = "market_closed_skip_strict_stale"
            elif candle_age_raw is not None and candle_age_raw <= threshold:
                blocker = False
                reason = "fallback_to_candle_within_threshold"
            else:
                blocker = True
                reason = "fallback_to_candle_exceeds_threshold"
        elif candle_ts is not None:
            blocker = True
            reason = "quote_timestamp_missing"
        else:
            blocker = True
            reason = "quote_missing"
    else:
        if quote_age_raw is not None and quote_age_raw < (-1.0 * skew_limit):
            blocker = True
            reason = "quote_in_future_clock_skew"
        elif not bool(market_open):
            blocker = False
            reason = "market_closed_skip_strict_stale"
        elif quote_age_raw is not None and quote_age_raw <= threshold:
            blocker = False
            reason = "quote_within_threshold"
        else:
            blocker = True
            reason = "quote_exceeds_threshold"

    return FreshnessDecision(
        symbol=str(symbol or "").upper(),
        instrument_token=_safe_int(instrument_token),
        decision_type=str(decision_type or "option_quote"),
        market_open=bool(market_open),
        now_epoch=now_ts,
        quote_epoch=quote_ts,
        candle_epoch=candle_ts,
        selected_epoch=selected_epoch,
        selected_source=selected_source,
        quote_age_sec=quote_age_raw,
        candle_age_sec=candle_age_raw,
        selected_age_sec=selected_age_raw,
        threshold_sec=threshold,
        blocker=bool(blocker),
        reason=reason,
        trade_id=str(trade_id).strip() if trade_id else None,
        ts_iso=_iso_utc(now_ts),
    )


def freshness_public_fields(decision: FreshnessDecision) -> dict[str, Any]:
    selected_age_non_negative = _non_negative_age(decision.selected_age_sec)
    quote_age_non_negative = _non_negative_age(decision.quote_age_sec)
    candle_age_non_negative = _non_negative_age(decision.candle_age_sec)
    return {
        "freshness_reason": decision.reason,
        "freshness_market_open": bool(decision.market_open),
        "freshness_now_epoch": float(decision.now_epoch),
        "freshness_quote_epoch": decision.quote_epoch,
        "freshness_candle_epoch": decision.candle_epoch,
        "freshness_threshold_sec": float(decision.threshold_sec),
        "freshness_selected_source": decision.selected_source,
        "freshness_selected_age_sec": decision.selected_age_sec,
        "quote_age_sec": selected_age_non_negative if decision.selected_source == "quote" else quote_age_non_negative,
        "candle_age_sec": candle_age_non_negative,
        "price_age_sec": selected_age_non_negative,
    }
