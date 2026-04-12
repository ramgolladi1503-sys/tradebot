from __future__ import annotations

from typing import Any


TRUST_BUCKET_TRUSTED = "trusted"
TRUST_BUCKET_NEAR_EXECUTABLE = "near_executable"
TRUST_BUCKET_DEGRADED = "degraded"


DEGRADED_REASON_CODES = {
    "WEAK_SIGNAL",
    "NO_SIGNAL",
    "RR_ESTIMATED_CONTEXT",
    "MISSING_RR_CONTEXT",
    "MISSING_LIQUIDITY_CONTEXT",
    "MISSING_SPREAD_CONTEXT",
    "MISSING_TIMING_CONTEXT",
    "MISSING_LIVE_TIMING_CONTEXT",
    "UNKNOWN_QUOTE_SOURCE",
    "EXECUTION_CONTEXT_DEGRADED",
}

CRITICAL_REASON_CODES = {
    "FEED_STALE",
    "NO_LIVE_OPTION_FEED",
    "UNRESOLVED_CONTRACT",
    "MISSING_CONTRACT_FIELDS",
    "MISSING_OPTION_TOKEN",
    "NO_TOKEN",
    "MISSING_ENTRY",
    "INVALID_LEVEL_GEOMETRY",
    "HARD_SPREAD_TOO_WIDE",
    "SPREAD_BREACHED",
    "EXECUTION_QUALITY_REJECT",
}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def candidate_reason_codes(candidate: dict[str, Any] | None) -> set[str]:
    if not isinstance(candidate, dict):
        return set()
    out: set[str] = set()
    for key in ("reject_reason", "reason", "execution_block_reason"):
        text = str(candidate.get(key) or "").strip().upper()
        if text:
            out.add(text)
    for key in (
        "gate_reasons",
        "blockers",
        "hard_blockers",
        "execution_blockers",
        "penalty_reasons",
        "confidence_penalty_reasons",
        "phase2_soft_penalties",
    ):
        for value in list(candidate.get(key) or []):
            text = str(value or "").strip().upper()
            if text:
                out.add(text)
    return out


def candidate_partition_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    symbol = str(candidate.get("symbol") or "").strip().upper()
    side = str(candidate.get("side") or candidate.get("direction") or "").strip().upper()
    expiry = str(candidate.get("expiry") or candidate.get("expiry_date") or "").strip().upper()
    option_type = str(candidate.get("option_type") or candidate.get("instrument_type") or "").strip().upper()
    strike = _safe_float(candidate.get("strike"))
    moneyness = str(candidate.get("moneyness_bucket") or candidate.get("moneyness") or "").strip().lower()
    thesis = str(
        candidate.get("setup_family")
        or candidate.get("strategy_family")
        or candidate.get("strategy_name")
        or candidate.get("candidate_origin")
        or ""
    ).strip().lower()
    return (symbol, side, expiry, option_type, strike, moneyness, thesis)


def candidate_trust_bucket(candidate: dict[str, Any]) -> str:
    codes = candidate_reason_codes(candidate)
    quote_source = str(candidate.get("quote_source") or "").strip().lower()
    execution_allowed = _safe_bool(candidate.get("execution_allowed"), default=True)
    tradable = _safe_bool(candidate.get("tradable"), default=True)
    execution_blocked = _safe_bool(candidate.get("execution_blocked"), default=False)
    queue_only = str(candidate.get("max_final_action") or "").strip().upper() == "QUEUE_ONLY"
    candidate_status = str(candidate.get("candidate_status") or "").strip().lower()
    execution_status = str(candidate.get("execution_status") or "").strip().lower()

    if codes & CRITICAL_REASON_CODES:
        return TRUST_BUCKET_DEGRADED
    if quote_source in {"", "unknown", "none"}:
        return TRUST_BUCKET_DEGRADED
    if codes & DEGRADED_REASON_CODES:
        return TRUST_BUCKET_DEGRADED
    if queue_only:
        return TRUST_BUCKET_NEAR_EXECUTABLE
    if candidate_status in {"near_executable", "queue_only", "scored"}:
        return TRUST_BUCKET_NEAR_EXECUTABLE
    if execution_status in {"queue_only", "scored"}:
        return TRUST_BUCKET_NEAR_EXECUTABLE
    if (not execution_allowed) or (not tradable) or execution_blocked:
        return TRUST_BUCKET_NEAR_EXECUTABLE
    return TRUST_BUCKET_TRUSTED


def annotate_candidate_partition(candidate: dict[str, Any]) -> dict[str, Any]:
    out = dict(candidate)
    bucket = candidate_trust_bucket(out)
    out["phase2_trust_bucket"] = bucket
    out["phase2_partition_key"] = candidate_partition_key(out)
    out["phase2_reason_codes"] = sorted(candidate_reason_codes(out))
    return out


def dedupe_partitioned_candidates(candidates: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    best_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for raw in list(candidates or []):
        candidate = annotate_candidate_partition(raw)
        key = candidate_partition_key(candidate)
        current = best_by_key.get(key)
        score = _safe_float(candidate.get("final_score")) or _safe_float(candidate.get("score")) or 0.0
        if current is None:
            best_by_key[key] = candidate
            continue
        current_score = _safe_float(current.get("final_score")) or _safe_float(current.get("score")) or 0.0
        if score > current_score:
            best_by_key[key] = candidate
    return list(best_by_key.values())


def partition_candidates(candidates: list[dict[str, Any]] | None) -> dict[str, list[dict[str, Any]]]:
    deduped = dedupe_partitioned_candidates(candidates)
    buckets = {
        TRUST_BUCKET_TRUSTED: [],
        TRUST_BUCKET_NEAR_EXECUTABLE: [],
        TRUST_BUCKET_DEGRADED: [],
    }
    for candidate in deduped:
        buckets[candidate["phase2_trust_bucket"]].append(candidate)
    for items in buckets.values():
        items.sort(
            key=lambda row: (
                _safe_float(row.get("final_score")) or _safe_float(row.get("score")) or 0.0,
                _safe_float(row.get("execution_score")) or 0.0,
                _safe_float(row.get("confidence_final")) or _safe_float(row.get("confidence")) or 0.0,
            ),
            reverse=True,
        )
    return buckets


def classify_no_trade_reason(partitions: dict[str, list[dict[str, Any]]], min_enter_score: float) -> str:
    trusted = list(partitions.get(TRUST_BUCKET_TRUSTED) or [])
    near_exec = list(partitions.get(TRUST_BUCKET_NEAR_EXECUTABLE) or [])
    degraded = list(partitions.get(TRUST_BUCKET_DEGRADED) or [])
    if not trusted and not near_exec and not degraded:
        return "no_rankable_candidates"
    if trusted:
        top = trusted[0]
        score = _safe_float(top.get("final_score")) or _safe_float(top.get("score")) or 0.0
        if score < float(min_enter_score):
            return "top_score_below_enter_threshold"
        return "trusted_candidate_available"
    if near_exec:
        return "only_near_executable_candidates"
    return "only_degraded_candidates"
