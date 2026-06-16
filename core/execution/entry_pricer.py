from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import time
from typing import Any


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        out = float(value)
        if math.isnan(out):
            return None
        return out
    except Exception:
        return None


def _positive_price(value: Any) -> float | None:
    out = _safe_float(value)
    if out is None or out <= 0:
        return None
    return out


def _quote_ts_epoch(snapshot: dict[str, Any] | None) -> float | None:
    if not isinstance(snapshot, dict):
        return None
    for key in ("ts", "timestamp", "quote_ts_epoch", "ltp_ts_epoch"):
        out = _safe_float(snapshot.get(key))
        if out is not None:
            return out / 1000.0 if out > 1e12 else out
    return None


def _quote_age_sec(*, now_epoch: float, quote_ts: float | None) -> float | None:
    if quote_ts is None:
        return None
    return now_epoch - quote_ts


@dataclass(frozen=True)
class ExecutionEntryDecision:
    execution_entry: float | None
    source: str
    executable: bool
    reason: str
    quote_age_sec: float | None
    threshold_sec: float | None
    bid: float | None
    ask: float | None
    quote_ts_epoch: float | None
    evaluated_at_epoch: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_execution_entry(
    *,
    side: str,
    bid: Any,
    ask: Any,
    snapshot: dict[str, Any] | None = None,
    evaluated_at_epoch: float | None = None,
    max_quote_age_sec: float | None = None,
) -> ExecutionEntryDecision:
    now_epoch = float(evaluated_at_epoch if evaluated_at_epoch is not None else time.time())
    side_key = str(side or "").strip().upper()
    bid_px = _positive_price(bid)
    ask_px = _positive_price(ask)
    quote_ts = _quote_ts_epoch(snapshot)
    quote_age_sec = _quote_age_sec(now_epoch=now_epoch, quote_ts=quote_ts)
    threshold_sec = None if max_quote_age_sec is None else max(0.0, float(max_quote_age_sec))

    if threshold_sec is not None:
        if quote_ts is None:
            return ExecutionEntryDecision(
                execution_entry=None,
                source="none",
                executable=False,
                reason="quote_timestamp_missing",
                quote_age_sec=None,
                threshold_sec=threshold_sec,
                bid=bid_px,
                ask=ask_px,
                quote_ts_epoch=quote_ts,
                evaluated_at_epoch=now_epoch,
            )
        if quote_age_sec is not None and quote_age_sec < 0:
            return ExecutionEntryDecision(
                execution_entry=None,
                source="none",
                executable=False,
                reason="future_quote_timestamp",
                quote_age_sec=quote_age_sec,
                threshold_sec=threshold_sec,
                bid=bid_px,
                ask=ask_px,
                quote_ts_epoch=quote_ts,
                evaluated_at_epoch=now_epoch,
            )
        if quote_age_sec is not None and quote_age_sec > threshold_sec:
            return ExecutionEntryDecision(
                execution_entry=None,
                source="none",
                executable=False,
                reason="stale_quote",
                quote_age_sec=quote_age_sec,
                threshold_sec=threshold_sec,
                bid=bid_px,
                ask=ask_px,
                quote_ts_epoch=quote_ts,
                evaluated_at_epoch=now_epoch,
            )

    if side_key == "BUY":
        if ask_px is not None:
            return ExecutionEntryDecision(
                execution_entry=ask_px,
                source="ask",
                executable=True,
                reason="ok",
                quote_age_sec=quote_age_sec,
                threshold_sec=threshold_sec,
                bid=bid_px,
                ask=ask_px,
                quote_ts_epoch=quote_ts,
                evaluated_at_epoch=now_epoch,
            )
        return ExecutionEntryDecision(
            execution_entry=None,
            source="none",
            executable=False,
            reason="missing_ask",
            quote_age_sec=quote_age_sec,
            threshold_sec=threshold_sec,
            bid=bid_px,
            ask=ask_px,
            quote_ts_epoch=quote_ts,
            evaluated_at_epoch=now_epoch,
        )

    if side_key == "SELL":
        if bid_px is not None:
            return ExecutionEntryDecision(
                execution_entry=bid_px,
                source="bid",
                executable=True,
                reason="ok",
                quote_age_sec=quote_age_sec,
                threshold_sec=threshold_sec,
                bid=bid_px,
                ask=ask_px,
                quote_ts_epoch=quote_ts,
                evaluated_at_epoch=now_epoch,
            )
        return ExecutionEntryDecision(
            execution_entry=None,
            source="none",
            executable=False,
            reason="missing_bid",
            quote_age_sec=quote_age_sec,
            threshold_sec=threshold_sec,
            bid=bid_px,
            ask=ask_px,
            quote_ts_epoch=quote_ts,
            evaluated_at_epoch=now_epoch,
        )

    return ExecutionEntryDecision(
        execution_entry=None,
        source="none",
        executable=False,
        reason="unsupported_side",
        quote_age_sec=quote_age_sec,
        threshold_sec=threshold_sec,
        bid=bid_px,
        ask=ask_px,
        quote_ts_epoch=quote_ts,
        evaluated_at_epoch=now_epoch,
    )
