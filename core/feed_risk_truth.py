from __future__ import annotations

from collections.abc import Iterable
from typing import Any

FEED_RISK_TOKENS: frozenset[str] = frozenset(
    {
        "fallback",
        "fallback_data",
        "fallback_quote_data",
        "fallback_quote_only",
        "iv_surface_slope",
        "low_iv_surface_confidence",
        "feed_health_hold",
        "no_live_option_feed",
        "price_mismatch",
        "recovered",
        "recovered_fallback",
        "rest_fallback",
        "stale_feed",
        "stale_option_ltp",
        "subscription_failed",
        "untrusted_quote_source",
        "synthetic",
        "missing_ltp",
        "missing_depth",
        "missing_spread",
        "quote_age_unknown",
        "advisory_only",
        "planning_only",
    }
)


def classify_feed_risk_reasons(
    *,
    safety_flags: Iterable[Any] = (),
    downgrade_reasons: Iterable[Any] = (),
    blockers: Iterable[Any] = (),
    warnings: Iterable[Any] = (),
    candidate_class: Any = None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    values = list(safety_flags) + list(downgrade_reasons) + list(blockers) + list(warnings)
    candidate_class_text = str(candidate_class or "").strip().lower()
    if candidate_class_text and candidate_class_text != "primary":
        values.append(candidate_class_text)
    for value in values:
        normalized = _normalize_token(value)
        if not normalized:
            continue
        if normalized in FEED_RISK_TOKENS:
            reasons.append(normalized)
        elif any(token in normalized for token in FEED_RISK_TOKENS):
            reasons.append(normalized)
    return tuple(sorted(set(reasons)))


def _normalize_token(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text.replace("-", "_").replace(" ", "_")


__all__ = ["FEED_RISK_TOKENS", "classify_feed_risk_reasons"]
