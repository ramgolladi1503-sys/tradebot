from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


QUOTE_AGE_TIMESTAMP_MISMATCH = "quote_age_timestamp_mismatch"
QUOTE_AGE_MISSING = "quote_age_missing"

QUOTE_TIMESTAMP_FIELDS = (
    "quote_ts_epoch",
    "option_ltp_timestamp",
    "last_option_tick_epoch",
    "ltp_ts_epoch",
    "quote_timestamp_epoch",
)

REPORTED_AGE_FIELDS = (
    "quote_age_sec",
    "price_age_sec",
    "option_ltp_age_sec",
    "ltp_age_sec",
)

OBSERVATION_EPOCH_FIELDS = (
    "decision_ts_epoch",
    "generated_at_epoch",
    "snapshot_ts_epoch",
    "display_ts_epoch",
    "event_ts_epoch",
    "timestamp_epoch",
    "ts_epoch",
    "created_at_epoch",
)

OBSERVATION_TS_FIELDS = (
    "decision_ts",
    "generated_at",
    "snapshot_ts",
    "timestamp",
    "ts_utc",
    "created_at",
)


@dataclass(frozen=True)
class QuoteAgeTruthDecision:
    ok: bool
    reason_code: str
    effective_age_sec: float | None = None
    reported_age_sec: float | None = None
    timestamp_age_sec: float | None = None
    quote_ts_epoch: float | None = None
    observation_epoch: float | None = None
    mismatch_delta_sec: float | None = None
    reported_age_field: str | None = None
    quote_timestamp_field: str | None = None
    observation_field: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _field_get(payload: Any, field: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(field)
    return getattr(payload, field, None)


def _source_flags(payload: Any) -> dict[str, Any]:
    flags = _field_get(payload, "source_flags") or {}
    return dict(flags) if isinstance(flags, dict) else {}


def _coerce_epoch(value: Any) -> float | None:
    numeric = _safe_float(value)
    if numeric is not None:
        if numeric > 10_000_000_000:
            return numeric / 1000.0
        return numeric
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return float(parsed.timestamp())
    except Exception:
        return None


def _first_value(payload: Any, flags: dict[str, Any], fields: tuple[str, ...]) -> tuple[str | None, Any]:
    for field in fields:
        value = _field_get(payload, field)
        if value not in (None, "", "None"):
            return field, value
        flag_value = flags.get(field)
        if flag_value not in (None, "", "None"):
            return f"source_flags.{field}", flag_value
    return None, None


def classify_quote_age_truth(
    payload: Any,
    *,
    now_epoch: float | None = None,
    mismatch_tolerance_sec: float = 5.0,
    require_age: bool = False,
) -> QuoteAgeTruthDecision:
    """Classify reported quote age against timestamp-derived quote age.

    The important rule is fail-closed on contradiction: if a row reports a fresh
    quote age but its quote timestamp proves an older quote, the effective age is
    the larger value and the decision is not OK.
    """
    flags = _source_flags(payload)
    timestamp_field, quote_ts_raw = _first_value(payload, flags, QUOTE_TIMESTAMP_FIELDS)
    reported_field, reported_age_raw = _first_value(payload, flags, REPORTED_AGE_FIELDS)
    observation_field, observation_raw = _first_value(payload, flags, OBSERVATION_EPOCH_FIELDS)
    if observation_raw in (None, "", "None"):
        observation_field, observation_raw = _first_value(payload, flags, OBSERVATION_TS_FIELDS)

    quote_ts_epoch = _coerce_epoch(quote_ts_raw)
    reported_age = _safe_float(reported_age_raw)
    observation_epoch = _coerce_epoch(observation_raw)
    if observation_epoch is None:
        observation_epoch = float(now_epoch if now_epoch is not None else time.time())
        observation_field = "now_epoch"

    timestamp_age = None
    if quote_ts_epoch is not None:
        timestamp_age = max(0.0, float(observation_epoch) - float(quote_ts_epoch))

    if reported_age is None and timestamp_age is None:
        return QuoteAgeTruthDecision(
            ok=not require_age,
            reason_code="ok" if not require_age else QUOTE_AGE_MISSING,
            observation_epoch=observation_epoch,
            observation_field=observation_field,
            context={"require_age": bool(require_age)},
        )

    effective_age = max(
        age for age in (reported_age, timestamp_age) if age is not None
    )

    mismatch_delta = None
    if reported_age is not None and timestamp_age is not None:
        mismatch_delta = abs(float(timestamp_age) - float(reported_age))
        if mismatch_delta > float(mismatch_tolerance_sec):
            return QuoteAgeTruthDecision(
                ok=False,
                reason_code=QUOTE_AGE_TIMESTAMP_MISMATCH,
                effective_age_sec=float(effective_age),
                reported_age_sec=float(reported_age),
                timestamp_age_sec=float(timestamp_age),
                quote_ts_epoch=quote_ts_epoch,
                observation_epoch=observation_epoch,
                mismatch_delta_sec=float(mismatch_delta),
                reported_age_field=reported_field,
                quote_timestamp_field=timestamp_field,
                observation_field=observation_field,
                context={
                    "mismatch_tolerance_sec": float(mismatch_tolerance_sec),
                    "require_age": bool(require_age),
                },
            )

    return QuoteAgeTruthDecision(
        ok=True,
        reason_code="ok",
        effective_age_sec=float(effective_age),
        reported_age_sec=None if reported_age is None else float(reported_age),
        timestamp_age_sec=None if timestamp_age is None else float(timestamp_age),
        quote_ts_epoch=quote_ts_epoch,
        observation_epoch=observation_epoch,
        mismatch_delta_sec=mismatch_delta,
        reported_age_field=reported_field,
        quote_timestamp_field=timestamp_field,
        observation_field=observation_field,
        context={
            "mismatch_tolerance_sec": float(mismatch_tolerance_sec),
            "require_age": bool(require_age),
        },
    )
