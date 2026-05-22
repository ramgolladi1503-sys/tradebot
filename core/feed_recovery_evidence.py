from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import config as cfg

FEED_RECOVERY_OK = "feed_recovery_ok"
FEED_RECOVERY_NOT_REQUIRED = "feed_recovery_not_required"
FEED_RECOVERY_BLOCKED = "feed_recovery_blocked"
STALE_FEED_DETECTED = "stale_feed_detected"
RECOVERY_ATTEMPT_ABSENT = "recovery_attempt_absent"
RECOVERY_RESULT_ABSENT = "recovery_result_absent"
RECOVERY_UNSUCCESSFUL = "recovery_unsuccessful"
FAIL_CLOSED_ABSENT = "fail_closed_absent"
UNSAFE_EXECUTION_ALLOWED = "unsafe_execution_allowed"


@dataclass(frozen=True)
class FeedRecoveryEvidence:
    recovery_ok: bool
    reason_code: str
    reasons: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)


def _get(payload: Any, field: str, default: Any = None) -> Any:
    return payload.get(field, default) if isinstance(payload, dict) else getattr(payload, field, default)


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", "None"):
            return value
    return None


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _append_unique(reasons: list[str], reason: str) -> None:
    if reason and reason not in reasons:
        reasons.append(reason)


def _max_age_sec() -> float:
    return float(getattr(cfg, "FEED_RECOVERY_EVIDENCE_MAX_AGE_SEC", getattr(cfg, "OPTION_LTP_SLA_SEC", 3.0)) or 3.0)


def _feed_age_sec(payload: Any) -> float | None:
    return _safe_float(
        _coalesce(
            _get(payload, "feed_age_sec"),
            _get(payload, "quote_age_sec"),
            _get(payload, "ltp_age_sec"),
            _get(payload, "age_sec"),
        )
    )


def _is_stale(payload: Any, max_age_sec: float) -> bool:
    explicit_state = str(_coalesce(_get(payload, "feed_state"), _get(payload, "data_state")) or "").strip().upper()
    if explicit_state in {"STALE", "DATA_STALE", "DEGRADED", "INVALID"}:
        return True
    explicit_flag = _coalesce(_get(payload, "stale_feed_detected"), _get(payload, "is_stale"), _get(payload, "stale"))
    if explicit_flag is not None:
        return _truthy(explicit_flag)
    age = _feed_age_sec(payload)
    return bool(age is not None and age > max_age_sec)


def _recovery_attempted(payload: Any) -> bool:
    return _truthy(
        _coalesce(
            _get(payload, "recovery_attempted"),
            _get(payload, "reconnect_attempted"),
            _get(payload, "resubscribe_attempted"),
            _get(payload, "refresh_attempted"),
        )
    )


def _recovery_successful(payload: Any, *, max_age_sec: float) -> bool | None:
    explicit = _coalesce(
        _get(payload, "recovery_successful"),
        _get(payload, "recovered"),
        _get(payload, "reconnect_successful"),
        _get(payload, "resubscribe_successful"),
    )
    if explicit is not None:
        return _truthy(explicit)
    post_age = _safe_float(
        _coalesce(
            _get(payload, "post_recovery_age_sec"),
            _get(payload, "recovered_feed_age_sec"),
            _get(payload, "post_refresh_age_sec"),
        )
    )
    if post_age is None:
        return None
    return post_age <= max_age_sec


def evaluate_feed_recovery_evidence(payload: Any) -> FeedRecoveryEvidence:
    """Evaluate stale-feed recovery evidence from a runtime snapshot.

    This function is pure and read-only. It does not reconnect, resubscribe,
    refresh market data, call a broker, or place orders. It only validates that
    a runtime/event payload proves stale-feed detection, a recovery attempt,
    recovery result, and fail-closed behavior.
    """
    max_age = _max_age_sec()
    stale = _is_stale(payload, max_age)
    fail_closed = _truthy(_coalesce(_get(payload, "fail_closed"), _get(payload, "execution_blocked"), _get(payload, "orders_blocked")))
    execution_allowed = _truthy(_coalesce(_get(payload, "execution_allowed"), _get(payload, "order_allowed"), False))
    attempt = _recovery_attempted(payload)
    success = _recovery_successful(payload, max_age_sec=max_age)
    reasons: list[str] = []

    if not stale:
        return FeedRecoveryEvidence(
            recovery_ok=True,
            reason_code=FEED_RECOVERY_NOT_REQUIRED,
            context={
                "stale_feed_detected": False,
                "feed_age_sec": _feed_age_sec(payload),
                "max_age_sec": max_age,
                "fail_closed": fail_closed,
                "execution_allowed": execution_allowed,
            },
        )

    _append_unique(reasons, STALE_FEED_DETECTED)
    if not attempt:
        _append_unique(reasons, RECOVERY_ATTEMPT_ABSENT)
    if success is None:
        _append_unique(reasons, RECOVERY_RESULT_ABSENT)
    elif not success:
        _append_unique(reasons, RECOVERY_UNSUCCESSFUL)
    if not fail_closed:
        _append_unique(reasons, FAIL_CLOSED_ABSENT)
    if execution_allowed and not success:
        _append_unique(reasons, UNSAFE_EXECUTION_ALLOWED)

    blocking_reasons = set(reasons) - {STALE_FEED_DETECTED}
    ok = bool(stale and attempt and success is True and fail_closed and not execution_allowed)
    return FeedRecoveryEvidence(
        recovery_ok=ok,
        reason_code=FEED_RECOVERY_OK if ok else FEED_RECOVERY_BLOCKED,
        reasons=tuple(reasons if not ok else (STALE_FEED_DETECTED, FEED_RECOVERY_OK)),
        context={
            "stale_feed_detected": stale,
            "recovery_attempted": attempt,
            "recovery_successful": success,
            "fail_closed": fail_closed,
            "execution_allowed": execution_allowed,
            "blocking_reasons": sorted(blocking_reasons),
            "feed_age_sec": _feed_age_sec(payload),
            "max_age_sec": max_age,
            "post_recovery_age_sec": _safe_float(
                _coalesce(
                    _get(payload, "post_recovery_age_sec"),
                    _get(payload, "recovered_feed_age_sec"),
                    _get(payload, "post_refresh_age_sec"),
                )
            ),
        },
    )
