from __future__ import annotations

from typing import Any, Mapping

LIVE_FALLBACK_EXECUTION_BLOCKED = "LIVE_FALLBACK_EXECUTION_BLOCKED"
LIVE_FALLBACK_EXECUTION_REASON = "live_fallback_execution_blocked"
LIVE_FALLBACK_CONTRACT_SCHEMA_VERSION = 1

_FALLBACK_BOOL_KEYS = {
    "synthetic_candidate",
    "forced_fallback_execution",
    "phase2_spread_fallback_used",
    "phase2_liquidity_fallback_used",
    "phase2_quote_age_fallback_used",
    "fallback_candidate",
    "fallback_used",
    "fallback_quote",
    "fallback_quote_used",
    "synthetic_quote",
    "synthetic_quote_used",
    "recovered_fallback",
    "recovered_fallback_candidate",
    "soft_reject_recovered",
    "softened_fallback_candidate",
}

_FALLBACK_TEXT_KEYS = {
    "quote_source",
    "candidate_origin",
    "strategy_family",
    "candidate_source",
    "quote_validation_status",
    "execution_quality_reason_code",
}

_FALLBACK_TEXT_MARKERS = {
    "",
    "UNKNOWN",
    "NONE",
    "FALLBACK",
    "SYNTHETIC",
    "RECOVERED_FALLBACK",
    "SOFTENED_BUILDER_PATH",
    "BUILDER_SOFT_REJECT",
}


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", "none", ""}:
        return False
    return False


def _live_mode(mode: str) -> bool:
    return str(mode or "").strip().upper() in {"LIVE", "REAL"}


def _append_unique(row: dict[str, Any], key: str, value: str) -> None:
    current = row.get(key)
    if isinstance(current, list):
        values = list(current)
    elif current in (None, ""):
        values = []
    else:
        values = [current]
    if value not in {str(item) for item in values}:
        values.append(value)
    row[key] = values


def is_fallback_execution_candidate(
    candidate: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(candidate, Mapping):
        return False
    contexts: list[Mapping[str, Any]] = [candidate]
    source_flags = candidate.get("source_flags")
    if isinstance(source_flags, Mapping):
        contexts.append(source_flags)

    for ctx in contexts:
        for key in _FALLBACK_BOOL_KEYS:
            if _boolish(ctx.get(key)):
                return True

    # Missing/unknown quote source is fallback-like for LIVE execution because
    # the orderable quote provenance is not proven. Other missing optional text
    # fields are not treated as fallback by absence alone.
    quote_source = str(candidate.get("quote_source") or "").strip().upper()
    if quote_source in {"", "UNKNOWN", "NONE", "FALLBACK", "SYNTHETIC"}:
        return True
    if "FALLBACK" in quote_source or "SYNTHETIC" in quote_source:
        return True

    for ctx in contexts:
        for key in _FALLBACK_TEXT_KEYS - {"quote_source"}:
            raw = ctx.get(key)
            if raw in (None, ""):
                continue
            text = str(raw).strip().upper()
            if text in _FALLBACK_TEXT_MARKERS:
                return True
            if "FALLBACK" in text or "SYNTHETIC" in text:
                return True
    return False


def enforce_live_fallback_execution_contract(
    candidate: Mapping[str, Any],
    mode: str,
) -> dict[str, Any]:
    """Return a candidate that cannot execute when LIVE fallback evidence exists.

    Non-LIVE modes are intentionally preserved. This is a read-only normalization
    contract used by callers/tests to prove that fallback rows may remain visible
    without becoming executable in LIVE.
    """

    row = dict(candidate or {})
    row["live_fallback_contract_schema_version"] = (
        LIVE_FALLBACK_CONTRACT_SCHEMA_VERSION
    )
    if not _live_mode(mode) or not is_fallback_execution_candidate(row):
        return row

    row["execution_allowed"] = False
    row["eligible_for_execution"] = False
    row["truth_allows_execution"] = False
    row["tradable"] = False
    row["execution_ok"] = False
    row["execution_blocked"] = True
    row["forced_fallback_execution"] = False
    row["selected_for_execution"] = False
    row["portfolio_optimization_selected"] = False
    row["selection_score"] = 0.0
    row["capital_assigned"] = 0.0
    row["allocated_capital"] = 0.0
    row["position_size_estimate"] = 0.0
    row["slot_id"] = None
    row["candidate_status"] = "watchlist"
    row["execution_status"] = "not_executable"
    row["execution_entry_status"] = "not_executable"
    row["max_final_action"] = "QUEUE_ONLY"
    row["final_action"] = "QUEUE_ONLY"
    row["permission"] = "QUEUE_ONLY"
    row["primary_blocker"] = LIVE_FALLBACK_EXECUTION_BLOCKED
    row["execution_block_reason"] = LIVE_FALLBACK_EXECUTION_REASON
    row["order_policy_reason"] = LIVE_FALLBACK_EXECUTION_REASON
    row["live_fallback_execution_blocked"] = True
    _append_unique(row, "hard_blockers", LIVE_FALLBACK_EXECUTION_BLOCKED)
    _append_unique(row, "blockers", LIVE_FALLBACK_EXECUTION_BLOCKED)
    _append_unique(row, "gate_reasons", LIVE_FALLBACK_EXECUTION_BLOCKED)

    source_flags = row.get("source_flags")
    if not isinstance(source_flags, dict):
        source_flags = {}
    source_flags["live_fallback_execution_blocked"] = True
    source_flags["order_policy_reason"] = LIVE_FALLBACK_EXECUTION_REASON
    row["source_flags"] = source_flags
    return row


__all__ = [
    "LIVE_FALLBACK_CONTRACT_SCHEMA_VERSION",
    "LIVE_FALLBACK_EXECUTION_BLOCKED",
    "LIVE_FALLBACK_EXECUTION_REASON",
    "enforce_live_fallback_execution_contract",
    "is_fallback_execution_candidate",
]
