from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


EXECUTION_CRITICAL_FIELDS = {
    "ltp",
    "opt_ltp",
    "current_ltp",
    "bid",
    "ask",
    "best_bid",
    "best_ask",
    "spread_pct",
    "liquidity_score",
    "instrument_token",
    "tradingsymbol",
    "instrument_id",
    "execution_entry",
    "quote_age_sec",
}

DIRTY_LINEAGES = {
    "FALLBACK_DEFAULT",
    "RECOVERED_PREVIOUS",
    "RECOVERED_FALLBACK",
    "REST_FALLBACK",
    "SYNTHETIC_OFFHOURS",
    "SYNTHETIC",
    "UNKNOWN",
}

SAFE_EXECUTION_ENTRY_SOURCES = {
    "ask",
    "bid",
    "last",
    "retained_prior_ask",
    "retained_prior_bid",
}

DIRTY_EXECUTION_ENTRY_SOURCES = {
    "recovered_fallback",
    "rest_fallback",
    "synthetic_offhours",
    "fallback",
    "unknown",
    "none",
    "",
}


@dataclass(frozen=True)
class DataQualityResult:
    data_quality_grade: str
    execution_truth_allowed: bool
    execution_truth_blockers: list[str] = field(default_factory=list)
    fallback_fields: list[str] = field(default_factory=list)
    lineage: dict[str, str] = field(default_factory=dict)
    data_quality_issues: list[str] = field(default_factory=list)

    def to_updates(self) -> dict[str, Any]:
        return {
            "data_quality_grade": self.data_quality_grade,
            "execution_truth_allowed": bool(self.execution_truth_allowed),
            "execution_truth_blockers": list(self.execution_truth_blockers),
            "fallback_fields": list(self.fallback_fields),
            "data_lineage": dict(self.lineage),
            "price_lineage": self.lineage.get("ltp", "UNKNOWN"),
            "spread_lineage": self.lineage.get("spread", "UNKNOWN"),
            "liquidity_lineage": self.lineage.get("liquidity", "UNKNOWN"),
            "contract_lineage": self.lineage.get("contract", "UNKNOWN"),
            "execution_entry_lineage": self.lineage.get("execution_entry", "UNKNOWN"),
            "data_quality_issues": list(self.data_quality_issues),
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


def _clean_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _append_unique(items: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def _source_flags(candidate: Mapping[str, Any]) -> dict[str, Any]:
    raw = candidate.get("source_flags") or {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def _candidate_get(candidate: Mapping[str, Any], key: str, default: Any = None) -> Any:
    if key in candidate:
        return candidate.get(key, default)
    flags = _source_flags(candidate)
    return flags.get(key, default)


def _is_present(value: Any) -> bool:
    return value not in (None, "", "None")


def _derive_lineage(candidate: Mapping[str, Any]) -> dict[str, str]:
    flags = _source_flags(candidate)
    quote_source = str(
        candidate.get("quote_source")
        or candidate.get("price_source")
        or flags.get("quote_source")
        or flags.get("price_source")
        or ""
    ).strip().lower()
    spread_source = str(
        candidate.get("spread_source")
        or flags.get("spread_source")
        or quote_source
        or ""
    ).strip().lower()
    liquidity_source = str(
        candidate.get("liquidity_source")
        or flags.get("liquidity_source")
        or spread_source
        or quote_source
        or ""
    ).strip().lower()
    execution_entry_source = str(
        candidate.get("execution_entry_source")
        or flags.get("execution_entry_source")
        or ""
    ).strip().lower()

    def quote_lineage(source: str) -> str:
        if source in {"kite", "broker", "live", "live_broker", "websocket", "depth_ws"}:
            return "LIVE_BROKER"
        if source in {"book", "live_book", "chain_cache", "option_chain"}:
            return "LIVE_BOOK"
        if source in {"rest", "rest_refresh"}:
            return "REST_REFRESH"
        if source in {"fallback", "fallback_default"}:
            return "FALLBACK_DEFAULT"
        if source in {"recovered_fallback", "recovered_previous"}:
            return "RECOVERED_FALLBACK"
        if source in {"synthetic", "synthetic_offhours"}:
            return "SYNTHETIC_OFFHOURS"
        return "UNKNOWN"

    lineage = {
        "ltp": quote_lineage(quote_source),
        "bid": quote_lineage(spread_source),
        "ask": quote_lineage(spread_source),
        "spread": quote_lineage(spread_source),
        "liquidity": quote_lineage(liquidity_source),
        "contract": "EXACT_MATCH" if _safe_bool(candidate.get("contract_exact_match"), False) else "UNKNOWN",
        "execution_entry": quote_lineage(execution_entry_source),
    }

    if execution_entry_source in SAFE_EXECUTION_ENTRY_SOURCES:
        lineage["execution_entry"] = execution_entry_source.upper()
    elif execution_entry_source in DIRTY_EXECUTION_ENTRY_SOURCES:
        lineage["execution_entry"] = "UNKNOWN" if execution_entry_source in {"", "none", "unknown"} else execution_entry_source.upper()

    if _safe_bool(candidate.get("phase2_spread_fallback_used"), False):
        lineage["spread"] = "FALLBACK_DEFAULT"
    if _safe_bool(candidate.get("phase2_liquidity_fallback_used"), False):
        lineage["liquidity"] = "FALLBACK_DEFAULT"
    if _safe_bool(candidate.get("fallback_used"), False):
        fallback_class = _clean_code(candidate.get("fallback_class") or flags.get("fallback_class"))
        if fallback_class:
            lineage["contract"] = fallback_class
        else:
            lineage["contract"] = "RECOVERED_FALLBACK"

    explicit_lineage = candidate.get("data_lineage") or flags.get("data_lineage")
    if isinstance(explicit_lineage, Mapping):
        for key, value in explicit_lineage.items():
            if key and value:
                lineage[str(key)] = _clean_code(value)

    for field_name, lineage_key in (
        ("price_lineage", "ltp"),
        ("spread_lineage", "spread"),
        ("liquidity_lineage", "liquidity"),
        ("contract_lineage", "contract"),
        ("execution_entry_lineage", "execution_entry"),
    ):
        value = candidate.get(field_name) or flags.get(field_name)
        if value:
            lineage[lineage_key] = _clean_code(value)

    return lineage


def assess_candidate_data_quality(
    candidate: Mapping[str, Any],
    *,
    max_quote_age_sec: float | None = None,
) -> DataQualityResult:
    """Return the canonical data-truth contract for a candidate.

    This function is intentionally conservative: if an execution-critical field is
    missing, fallback-derived, synthetic, recovered, stale, or unknown, execution
    truth is blocked. The candidate may still be useful as advisory/debug output.
    """
    candidate = dict(candidate or {})
    flags = _source_flags(candidate)
    blockers: list[str] = []
    issues: list[str] = []
    fallback_fields: list[str] = []
    lineage = _derive_lineage(candidate)

    quote_age = _safe_float(candidate.get("quote_age_sec") or flags.get("quote_age_sec"))
    if max_quote_age_sec is None:
        max_quote_age_sec = _safe_float(candidate.get("max_quote_age_sec") or flags.get("max_quote_age_sec"))
    if max_quote_age_sec is not None and quote_age is not None and quote_age > max_quote_age_sec:
        _append_unique(blockers, "stale_quote")
        _append_unique(issues, "stale_quote")
    if quote_age is None:
        _append_unique(blockers, "missing_quote_age")
        _append_unique(issues, "missing_quote_age")

    ltp = _safe_float(
        candidate.get("opt_ltp")
        or candidate.get("current_ltp")
        or candidate.get("ltp")
        or flags.get("opt_ltp")
        or flags.get("current_ltp")
    )
    bid = _safe_float(candidate.get("best_bid") or candidate.get("bid") or flags.get("best_bid") or flags.get("bid"))
    ask = _safe_float(candidate.get("best_ask") or candidate.get("ask") or flags.get("best_ask") or flags.get("ask"))
    spread_pct = _safe_float(candidate.get("spread_pct") or flags.get("spread_pct"))
    liquidity_score = _safe_float(candidate.get("liquidity_score") or flags.get("liquidity_score"))
    execution_entry = _safe_float(candidate.get("execution_entry") or flags.get("execution_entry"))
    execution_entry_status = str(candidate.get("execution_entry_status") or flags.get("execution_entry_status") or "").strip().lower()
    execution_entry_source = str(candidate.get("execution_entry_source") or flags.get("execution_entry_source") or "").strip().lower()

    if ltp is None or ltp <= 0:
        _append_unique(blockers, "missing_option_ltp")
        _append_unique(issues, "missing_option_ltp")
    if bid is None or ask is None:
        _append_unique(blockers, "missing_bid_ask")
        _append_unique(issues, "missing_bid_ask")
    if spread_pct is None:
        _append_unique(blockers, "missing_spread")
        _append_unique(issues, "missing_spread")
    if liquidity_score is None:
        _append_unique(blockers, "missing_liquidity_score")
        _append_unique(issues, "missing_liquidity_score")
    if execution_entry is None or execution_entry_status != "executable":
        _append_unique(blockers, "missing_execution_entry")
        _append_unique(issues, "missing_execution_entry")
    if execution_entry_source in DIRTY_EXECUTION_ENTRY_SOURCES:
        _append_unique(blockers, "dirty_execution_entry_source")
        _append_unique(issues, f"dirty_execution_entry_source:{execution_entry_source or 'empty'}")

    if _safe_bool(candidate.get("phase2_spread_fallback_used") or flags.get("phase2_spread_fallback_used"), False):
        _append_unique(fallback_fields, "spread_pct")
        _append_unique(blockers, "fallback_spread")
        _append_unique(issues, "fallback_spread")
    if _safe_bool(candidate.get("phase2_liquidity_fallback_used") or flags.get("phase2_liquidity_fallback_used"), False):
        _append_unique(fallback_fields, "liquidity_score")
        _append_unique(blockers, "fallback_liquidity")
        _append_unique(issues, "fallback_liquidity")
    if _safe_bool(candidate.get("phase2_spread_fallback_used"), False) and "spread_pct" not in fallback_fields:
        fallback_fields.append("spread_pct")

    existing_fallback_fields = candidate.get("fallback_fields") or flags.get("fallback_fields") or []
    if isinstance(existing_fallback_fields, (list, tuple, set)):
        for field_name in existing_fallback_fields:
            _append_unique(fallback_fields, str(field_name))
    elif existing_fallback_fields:
        _append_unique(fallback_fields, str(existing_fallback_fields))

    for field_name in fallback_fields:
        if field_name in EXECUTION_CRITICAL_FIELDS:
            _append_unique(blockers, f"fallback_{field_name}")
            _append_unique(issues, f"fallback_{field_name}")

    quote_source = str(candidate.get("quote_source") or flags.get("quote_source") or "").strip().lower()
    if quote_source in {"", "unknown", "none"}:
        _append_unique(blockers, "unknown_quote_source")
        _append_unique(issues, "unknown_quote_source")

    for key, value in lineage.items():
        normalized = _clean_code(value)
        if normalized in DIRTY_LINEAGES or normalized.startswith("FALLBACK") or normalized.startswith("RECOVERED"):
            _append_unique(issues, f"dirty_lineage:{key}:{normalized}")
            if key in {"ltp", "bid", "ask", "spread", "liquidity", "contract", "execution_entry"}:
                _append_unique(blockers, f"dirty_{key}_lineage")

    if blockers:
        if any(code.startswith("missing_") for code in blockers):
            grade = "F"
        elif any("fallback" in code or "dirty" in code or "unknown" in code or "stale" in code for code in blockers):
            grade = "D"
        else:
            grade = "C"
    else:
        grade = "A"

    return DataQualityResult(
        data_quality_grade=grade,
        execution_truth_allowed=not blockers,
        execution_truth_blockers=blockers,
        fallback_fields=fallback_fields,
        lineage=lineage,
        data_quality_issues=issues,
    )


def apply_data_quality_contract(
    candidate: Mapping[str, Any],
    *,
    max_quote_age_sec: float | None = None,
) -> dict[str, Any]:
    """Return a candidate copy enriched with the canonical data-quality contract."""
    out = dict(candidate or {})
    result = assess_candidate_data_quality(out, max_quote_age_sec=max_quote_age_sec)
    updates = result.to_updates()
    out.update(updates)
    source_flags = dict(out.get("source_flags") or {})
    source_flags.update({key: value for key, value in updates.items() if key != "source_flags"})
    out["source_flags"] = source_flags
    if not result.execution_truth_allowed:
        out["execution_allowed"] = False
        out["eligible_for_execution"] = False
        out["selected_for_execution"] = False
        out["is_executable"] = False
        out.setdefault("capital_assigned", 0.0)
    return out
