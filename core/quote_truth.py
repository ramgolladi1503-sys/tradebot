from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from config import config as cfg
from core.quote_age_truth import QUOTE_AGE_TIMESTAMP_MISMATCH, classify_quote_age_truth


_PRESERVE_STATUSES = {
    "DISPLAYABLE",
    "NON_EXECUTABLE",
    "OFFHOURS_SYNTHETIC",
    "PRICE_MISMATCH",
    "REST_FALLBACK",
}

TRUSTED_QUOTE_SOURCES = {
    "LIVE",
    "WEBSOCKET",
    "WS",
    "KITE_WS",
    "DEPTH_WS",
    "OPTION_WS",
}

CACHE_QUOTE_SOURCES = {
    "TICK_STORE",
    "QUOTE_CACHE",
    "DEPTH_STORE",
}

FALLBACK_QUOTE_SOURCES = {
    "FALLBACK",
    "REST_FALLBACK",
    "RECOVERED_FALLBACK",
    "FALLBACK_RECOVERED",
    "QUOTE_FALLBACK",
    "CLOSE_FALLBACK",
    "DERIVED_FALLBACK",
    "SYNTHETIC_OFFHOURS",
}

SUBSCRIPTION_FAILED_SOURCES = {
    "SUBSCRIPTION_FAILED",
    "OPTION_SUBSCRIPTION_FAILED",
}

QUOTE_TRUTH_BLOCK_REASON = "quote_truth_contract_failed"
QUOTE_SOURCE_UNKNOWN_REASON = "quote_source_unknown"
QUOTE_SOURCE_FALLBACK_REASON = "fallback_quote_source"
QUOTE_SOURCE_SUBSCRIPTION_FAILED_REASON = "subscription_failed_quote"
QUOTE_PRICE_MISMATCH_REASON = "price_mismatch_quote"
QUOTE_STALE_REASON = "stale_option_ltp"
QUOTE_NO_LIVE_FEED_REASON = "no_live_option_feed"
QUOTE_AGE_MISSING_REASON = "quote_age_missing"


@dataclass(frozen=True)
class QuoteTruthDecision:
    truth_ok: bool
    rank_eligible: bool
    execution_eligible: bool
    reason_code: str
    reasons: tuple[str, ...] = ()
    quote_source: str | None = None
    option_ltp_source: str | None = None
    source_trust: str = "unknown"
    quote_validation_status: str = "OK"
    effective_age_sec: float | None = None
    age_reason_code: str = "ok"
    context: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


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


def _lower(value: Any) -> str:
    if value in (None, "", "None"):
        return ""
    return str(value).strip().lower()


def _candidate_get(payload: Any, field: str, default: Any = None) -> Any:
    return payload.get(field, default) if isinstance(payload, dict) else getattr(payload, field, default)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _source_flags(payload: Any) -> dict[str, Any]:
    return _mapping(_candidate_get(payload, "source_flags", {}) or {})


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", "None"):
            return value
    return None


def _append_unique(reasons: list[str], reason: str | None) -> None:
    text = str(reason or "").strip()
    if text and text not in reasons:
        reasons.append(text)


def _quote_band_tolerance_pct() -> float:
    tol = _safe_float(getattr(cfg, "OPTION_LAST_OUTSIDE_BAND_PCT", 0.01))
    if tol is None or tol < 0:
        return 0.01
    return float(tol)


def _max_quote_age_sec(explicit: Any = None) -> float:
    max_age = _safe_float(explicit)
    if max_age is None or max_age <= 0:
        max_age = _safe_float(getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8.0)) or 8.0
    return float(max_age)


def _quote_truth_maps(payload: Any, flags: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    direct = _mapping(_candidate_get(payload, "quote_truth"))
    flagged = _mapping(flags.get("quote_truth"))
    snapshot_direct = _mapping(_candidate_get(payload, "quote_truth_snapshot"))
    snapshot_flagged = _mapping(flags.get("quote_truth_snapshot"))
    truth = dict(flagged)
    truth.update(direct)
    snapshot = dict(snapshot_flagged)
    snapshot.update(snapshot_direct)
    return truth, snapshot


def _first_quote_value(payload: Any, flags: dict[str, Any], fields: tuple[str, ...]) -> Any:
    truth, snapshot = _quote_truth_maps(payload, flags)
    for field in fields:
        value = _coalesce(
            _candidate_get(payload, field),
            flags.get(field),
            truth.get(field),
            snapshot.get(field),
        )
        if value not in (None, "", "None"):
            return value
    return None


def _all_sources(payload: Any, flags: dict[str, Any]) -> set[str]:
    truth, snapshot = _quote_truth_maps(payload, flags)
    values = {
        _candidate_get(payload, "quote_source"),
        flags.get("quote_source"),
        _candidate_get(payload, "option_ltp_source"),
        flags.get("option_ltp_source"),
        _candidate_get(payload, "price_source"),
        flags.get("price_source"),
        _candidate_get(payload, "execution_entry_source"),
        flags.get("execution_entry_source"),
        _candidate_get(payload, "entry_source"),
        flags.get("entry_source"),
        truth.get("quote_source"),
        truth.get("option_ltp_source"),
        snapshot.get("quote_source"),
        snapshot.get("option_ltp_source"),
    }
    return {_text(value) for value in values if _text(value)}


def _source_trust(sources: set[str]) -> str:
    if not sources:
        return "unknown"
    if sources.intersection(SUBSCRIPTION_FAILED_SOURCES):
        return "subscription_failed"
    if sources.intersection(FALLBACK_QUOTE_SOURCES):
        return "fallback"
    if sources.intersection(TRUSTED_QUOTE_SOURCES):
        return "trusted_live"
    if sources.intersection(CACHE_QUOTE_SOURCES):
        return "trusted_cache"
    return "unknown"


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
    max_age = _max_quote_age_sec(max_quote_age_sec)

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


def classify_quote_truth(
    payload: Any,
    *,
    max_quote_age_sec: Any = None,
    mismatch_tolerance_sec: float | None = None,
    require_source: bool = False,
    require_age: bool = False,
) -> QuoteTruthDecision:
    """Return the canonical quote-truth decision for rank/execution eligibility.

    The contract centralizes source trust, validation status, timestamp/age truth,
    and final rank/execution eligibility. Legacy callers may keep
    ``require_source=False`` while new execution-grade gates can opt into strict
    source proof.
    """
    flags = _source_flags(payload)
    quote_source = _first_quote_value(payload, flags, ("quote_source", "price_source", "entry_source"))
    option_ltp_source = _first_quote_value(payload, flags, ("option_ltp_source", "execution_entry_source"))
    sources = _all_sources(payload, flags)
    source_trust = _source_trust(sources)
    max_age = _max_quote_age_sec(max_quote_age_sec)
    tolerance = float(
        mismatch_tolerance_sec
        if mismatch_tolerance_sec is not None
        else getattr(cfg, "QUOTE_AGE_MISMATCH_TOLERANCE_SEC", 5.0)
    )
    age_decision = classify_quote_age_truth(
        payload,
        mismatch_tolerance_sec=max(0.0, tolerance),
        require_age=bool(require_age),
    )
    effective_age = age_decision.effective_age_sec
    existing_status = _first_quote_value(
        payload,
        flags,
        ("quote_validation_status", "validation_status", "validation_issue_code"),
    )
    validation_status = resolve_quote_validation_status(
        existing_status=existing_status,
        current_ltp=_first_quote_value(payload, flags, ("current_ltp", "option_ltp", "ltp")),
        quote_age_sec=effective_age,
        best_bid=_first_quote_value(payload, flags, ("best_bid", "bid")),
        best_ask=_first_quote_value(payload, flags, ("best_ask", "ask")),
        max_quote_age_sec=max_age,
    )

    reasons: list[str] = []
    if require_source and source_trust == "unknown":
        _append_unique(reasons, QUOTE_SOURCE_UNKNOWN_REASON)
    if source_trust == "fallback" or validation_status == "REST_FALLBACK":
        _append_unique(reasons, QUOTE_SOURCE_FALLBACK_REASON)
    if source_trust == "subscription_failed":
        _append_unique(reasons, QUOTE_SOURCE_SUBSCRIPTION_FAILED_REASON)
    if validation_status == "PRICE_MISMATCH":
        _append_unique(reasons, QUOTE_PRICE_MISMATCH_REASON)
    if validation_status == "STALE_OPTION_LTP":
        _append_unique(reasons, QUOTE_STALE_REASON)
    if validation_status == "NO_LIVE_OPTION_FEED":
        _append_unique(reasons, QUOTE_NO_LIVE_FEED_REASON)
    if age_decision.reason_code == QUOTE_AGE_TIMESTAMP_MISMATCH:
        _append_unique(reasons, QUOTE_AGE_TIMESTAMP_MISMATCH)
    if require_age and effective_age is None:
        _append_unique(reasons, QUOTE_AGE_MISSING_REASON)
    if effective_age is not None and effective_age > max_age:
        _append_unique(reasons, QUOTE_STALE_REASON)

    truth_ok = not reasons
    eligibility_ok = truth_ok and source_trust in {"trusted_live", "trusted_cache", "unknown"}
    return QuoteTruthDecision(
        truth_ok=truth_ok,
        rank_eligible=eligibility_ok,
        execution_eligible=eligibility_ok,
        reason_code="ok" if truth_ok else QUOTE_TRUTH_BLOCK_REASON,
        reasons=tuple(reasons),
        quote_source=None if quote_source in (None, "", "None") else _lower(quote_source),
        option_ltp_source=None if option_ltp_source in (None, "", "None") else _lower(option_ltp_source),
        source_trust=source_trust,
        quote_validation_status=validation_status,
        effective_age_sec=effective_age,
        age_reason_code=age_decision.reason_code,
        context={
            "sources": sorted(sources),
            "max_quote_age_sec": max_age,
            "age_truth": age_decision.__dict__,
            "quote_consistency_score": quote_consistency_score(
                current_ltp=_first_quote_value(payload, flags, ("current_ltp", "option_ltp", "ltp")),
                best_bid=_first_quote_value(payload, flags, ("best_bid", "bid")),
                best_ask=_first_quote_value(payload, flags, ("best_ask", "ask")),
            ),
            "require_source": bool(require_source),
            "require_age": bool(require_age),
        },
    )
