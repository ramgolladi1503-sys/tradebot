from __future__ import annotations

from typing import Any

TRUTH_REAL = "REAL"
TRUTH_DEGRADED = "DEGRADED"
TRUTH_FALLBACK = "FALLBACK"
TRUTH_SYNTHETIC = "SYNTHETIC"

TRUTH_CAP = {
    TRUTH_REAL: "EXECUTE",
    TRUTH_DEGRADED: "QUEUE_ONLY",
    TRUTH_FALLBACK: "ADVISORY_ONLY",
    TRUTH_SYNTHETIC: "ADVISORY_ONLY",
}

FALLBACK_ORIGINS = {"fallback", "fallback_min_breadth", "recovered_fallback", "rest_fallback", "synthetic_offhours"}
# Planning and invalid snapshots are synthetic. Softened weak/no-signal candidates are not
# synthetic by themselves; decision_engine handles them as QUEUE_ONLY so reason contracts stay stable.
SYNTHETIC_ORIGINS = {"pre_builder_gate", "invalid_snapshot", "planning_only"}
FALLBACK_ENTRY_SOURCES = {"recovered_fallback", "rest_fallback", "synthetic_offhours", "fallback"}
DEGRADED_REASONS = {
    "stale_quote",
    "low_data_confidence",
    "unverified_spread",
    "missing_liquidity_validation",
    "unknown_quote_source",
    "execution_context_degraded",
}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _get(candidate: Any, key: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(key, default)
    return getattr(candidate, key, default)


def _flags(candidate: Any) -> dict[str, Any]:
    value = _get(candidate, "source_flags", {})
    return value if isinstance(value, dict) else {}


def reason_codes(candidate: Any) -> set[str]:
    out: set[str] = set()
    for key in (
        "reason",
        "reject_reason",
        "entry_block_code",
        "permission_reason",
        "execution_block_reason",
        "order_policy_reason",
        "quote_validation_status",
    ):
        value = str(_get(candidate, key, "") or "").strip().lower()
        if value:
            out.add(value)
    for key in ("gate_reasons", "blockers", "hard_blockers", "execution_blockers", "phase2_soft_penalties", "warnings"):
        for item in list(_get(candidate, key, []) or []):
            value = str(item or "").strip().lower()
            if value:
                out.add(value)
    flags = _flags(candidate)
    for key in ("soft_reject_reason", "candidate_origin", "order_policy_reason"):
        value = str(flags.get(key) or "").strip().lower()
        if value:
            out.add(value)
    return out


def derive_truth_quality(candidate: Any) -> str:
    explicit = str(_get(candidate, "truth_quality", "") or "").strip().upper()
    if explicit in {TRUTH_REAL, TRUTH_DEGRADED, TRUTH_FALLBACK, TRUTH_SYNTHETIC}:
        return explicit

    flags = _flags(candidate)
    origin = str(
        _get(candidate, "candidate_origin", "")
        or flags.get("candidate_origin")
        or flags.get("origin")
        or flags.get("source")
        or ""
    ).strip().lower()
    row_kind = str(_get(candidate, "row_kind", "") or "").strip().lower()
    entry_source = str(_get(candidate, "execution_entry_source", "") or "").strip().lower()
    strategy_family = str(_get(candidate, "strategy_family", "") or "").strip().lower()
    candidate_type = str(_get(candidate, "candidate_type", "") or "").strip().lower()
    candidate_class = str(_get(candidate, "candidate_class", "") or "").strip().lower()
    trade_id = str(_get(candidate, "trade_id", "") or "").strip().lower()

    if (
        row_kind in FALLBACK_ORIGINS
        or bool(flags.get("fallback_candidate"))
        or bool(flags.get("recovered_fallback"))
        or origin in FALLBACK_ORIGINS
        or entry_source in FALLBACK_ENTRY_SOURCES
        or bool(_get(candidate, "phase2_spread_fallback_used", False))
        or bool(_get(candidate, "phase2_liquidity_fallback_used", False))
    ):
        return TRUTH_FALLBACK

    if (
        candidate_class == "synthetic"
        or origin in SYNTHETIC_ORIGINS
        or strategy_family in {"synthetic_advisory", "builder_soft_reject"}
        or candidate_type == "fallback_market_candidate"
        or trade_id.startswith(("softrej_", "tbsoft_"))
        or bool(_get(candidate, "planning_only", False))
    ):
        return TRUTH_SYNTHETIC

    quote_source = str(_get(candidate, "quote_source", "") or flags.get("quote_source") or "").strip().lower()
    data_confidence = _safe_float(_get(candidate, "data_confidence", flags.get("data_confidence")))
    quote_age = _safe_float(_get(candidate, "quote_age_sec", flags.get("quote_age_sec")))
    spread_pct = _safe_float(_get(candidate, "spread_pct", flags.get("spread_pct")))
    quote_ok = bool(_get(candidate, "quote_ok", True))

    # Explicit real class in tests/controlled fixtures should not be punished only for
    # missing quote_source when quote/spread/age are otherwise present and healthy.
    if candidate_class == "real" and quote_ok and quote_age is not None and quote_age <= 2.0 and spread_pct is not None:
        return TRUTH_REAL

    if reason_codes(candidate) & DEGRADED_REASONS:
        return TRUTH_DEGRADED
    if quote_source in {"unknown", "none"}:
        return TRUTH_DEGRADED
    if data_confidence is not None and data_confidence < 0.45:
        return TRUTH_DEGRADED
    if quote_age is not None and quote_age > 2.0:
        return TRUTH_DEGRADED
    if spread_pct is None and quote_source in {"", "unknown", "none"}:
        return TRUTH_DEGRADED
    return TRUTH_REAL


def truth_cap(truth_quality: str) -> str:
    return TRUTH_CAP.get(str(truth_quality or "").strip().upper(), "ADVISORY_ONLY")


def apply_truth_quality_contract(candidate: dict[str, Any]) -> dict[str, Any]:
    out = dict(candidate or {})
    truth_quality = derive_truth_quality(out)
    cap = truth_cap(truth_quality)
    out["truth_quality"] = truth_quality
    out["truth_execution_cap"] = cap
    if cap == "ADVISORY_ONLY":
        out.update(
            {
                "permission": "ADVISORY_ONLY",
                "final_action": "ADVISORY_ONLY",
                "execution_status": "advisory_only",
                "candidate_status": "advisory_only",
                "execution_allowed": False,
                "eligible_for_execution": False,
                "tradable": False,
                "is_executable": False,
                "truth_block_reason": f"truth_quality_{truth_quality.lower()}",
            }
        )
    elif cap == "QUEUE_ONLY" and str(out.get("final_action") or "").strip().upper() == "EXECUTE":
        out.update(
            {
                "permission": "QUEUE_ONLY",
                "final_action": "QUEUE_ONLY",
                "execution_status": "queue_only",
                "execution_allowed": False,
                "eligible_for_execution": False,
                "is_executable": False,
                "truth_block_reason": "truth_quality_degraded",
            }
        )
    return out
