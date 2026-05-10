from __future__ import annotations

from typing import Any, Mapping


def _as_list(value: Any) -> list[str]:
    if value in (None, "", "None"):
        return []
    if isinstance(value, (list, tuple, set)):
        raw = value
    else:
        raw = [value]
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _append_unique(items: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def stamp_fallback_lineage(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    """Stamp explicit lineage when fallback/default data is present.

    This helper is safe to use immediately after fallback fill logic. It does not
    decide trades. It makes fallback truth visible so finalization, allocation,
    risk, review, reports, and dashboard can block or explain it consistently.
    """
    out = dict(candidate or {})
    source_flags = dict(out.get("source_flags") or {})
    fallback_fields = _as_list(out.get("fallback_fields") or source_flags.get("fallback_fields"))
    data_lineage = dict(out.get("data_lineage") or source_flags.get("data_lineage") or {})

    if bool(out.get("phase2_spread_fallback_used") or source_flags.get("phase2_spread_fallback_used")):
        _append_unique(fallback_fields, "spread_pct")
        out["spread_lineage"] = "FALLBACK_DEFAULT"
        data_lineage["spread"] = "FALLBACK_DEFAULT"
        source_flags["spread_lineage"] = "FALLBACK_DEFAULT"

    if bool(out.get("phase2_liquidity_fallback_used") or source_flags.get("phase2_liquidity_fallback_used")):
        _append_unique(fallback_fields, "liquidity_score")
        out["liquidity_lineage"] = "FALLBACK_DEFAULT"
        data_lineage["liquidity"] = "FALLBACK_DEFAULT"
        source_flags["liquidity_lineage"] = "FALLBACK_DEFAULT"

    if bool(out.get("phase2_quote_age_fallback_used") or source_flags.get("phase2_quote_age_fallback_used")):
        _append_unique(fallback_fields, "quote_age_sec")
        out["quote_age_lineage"] = "FALLBACK_DEFAULT"
        data_lineage["quote_age"] = "FALLBACK_DEFAULT"
        source_flags["quote_age_lineage"] = "FALLBACK_DEFAULT"

    if bool(out.get("fallback_used") or source_flags.get("fallback_used")):
        fallback_class = str(out.get("fallback_class") or source_flags.get("fallback_class") or "RECOVERED_FALLBACK").strip().upper()
        out["contract_lineage"] = fallback_class or "RECOVERED_FALLBACK"
        data_lineage["contract"] = out["contract_lineage"]
        source_flags["contract_lineage"] = out["contract_lineage"]

    quote_source = str(out.get("quote_source") or source_flags.get("quote_source") or "").strip().lower()
    if quote_source in {"", "unknown", "none"}:
        out["price_lineage"] = "UNKNOWN"
        data_lineage.setdefault("ltp", "UNKNOWN")
        source_flags["price_lineage"] = "UNKNOWN"

    execution_entry_source = str(out.get("execution_entry_source") or source_flags.get("execution_entry_source") or "").strip().lower()
    if execution_entry_source in {"recovered_fallback", "rest_fallback", "synthetic_offhours", "fallback", "unknown"}:
        _append_unique(fallback_fields, "execution_entry")
        out["execution_entry_lineage"] = execution_entry_source.upper()
        data_lineage["execution_entry"] = out["execution_entry_lineage"]
        source_flags["execution_entry_lineage"] = out["execution_entry_lineage"]

    out["fallback_fields"] = fallback_fields
    out["data_lineage"] = data_lineage
    source_flags["fallback_fields"] = fallback_fields
    source_flags["data_lineage"] = data_lineage
    out["source_flags"] = source_flags
    return out
