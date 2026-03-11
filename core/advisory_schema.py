from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.entry_semantics import (
    DISPLAY_ENTRY_STATUSES,
    ENTRY_SOURCE_ENUM,
    EXECUTION_ENTRY_STATUSES,
    EntryContractViolation,
    build_entry_state,
)
from core.issue_policy import (
    ISSUE_CATEGORY_HARD,
    ISSUE_CATEGORY_SOFT,
    ISSUE_CATEGORY_WARNING,
    classify_issue,
)
from core.paths import logs_dir
from core.trade_identity import derive_strategy_id


class AdvisorySchemaError(ValueError):
    pass


ENTRY_STATUSES = set(DISPLAY_ENTRY_STATUSES)
READINESS_STATES = {"READY", "QUEUE_ONLY", "ADVISORY_ONLY", "BLOCKED"}
EXECUTION_STATUSES = {"blocked", "advisory_only", "queue_only", "executable"}
QUOTE_SOURCES = {
    "tick_store",
    "rest_fallback",
    "synthetic_offhours",
    "subscription_failed",
    "option_chain_meta",
    "option_chain_live",
    "live",
    "depth",
    "depth_ws",
    "rest_quote",
    "synthetic_index",
    "missing_depth",
    "missing_ltp",
    "stale_ltp",
    "none",
    "unknown",
}
REQUIRED_FIELDS = (
    "trade_id",
    "strategy_id",
    "advisory_id",
    "symbol",
    "strategy_name",
    "timestamp",
    "instrument_type",
    "execution_entry",
    "execution_entry_source",
    "execution_entry_status",
    "display_entry",
    "display_entry_source",
    "display_entry_status",
    "entry_reason",
    "entry_clear_reason",
    "entry",
    "entry_status",
    "entry_source",
    "confidence",
    "readiness",
    "blockers",
    "hard_blockers",
    "soft_penalties",
    "warnings",
    "quote_source",
    "quote_age_sec",
    "decision_explain",
    "market_open",
)
_LEGACY_NON_ERROR_ENTRY_STATUSES = {"VALID", "OK", "LIVE_OK", "REST_FALLBACK", "OFFHOURS_SYNTHETIC"}
_LIST_FIELDS = ("hard_blockers", "soft_penalties", "warnings")


def advisory_schema_error_path() -> Path:
    return logs_dir() / "advisory_schema_errors.jsonl"


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def log_advisory_schema_error(source: str, payload: Any, error: Exception | str) -> None:
    row = payload if isinstance(payload, dict) else {}
    _append_jsonl(
        advisory_schema_error_path(),
        {
            "ts_epoch": datetime.now(timezone.utc).timestamp(),
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "source": str(source or "unknown"),
            "error": str(error),
            "advisory_id": row.get("advisory_id") or row.get("trade_id") or row.get("trade_key"),
            "trade_id": row.get("trade_id"),
            "symbol": row.get("symbol"),
            "entry_status": row.get("entry_status"),
            "readiness": row.get("readiness"),
            "present_fields": sorted(str(key) for key in row.keys()),
        },
    )


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        out = float(value)
        return out
    except Exception:
        return None


def _normalize_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _safe_lower_text(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text or None


def _normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return None


def _normalize_blockers(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            text = _normalize_text(item)
            if text and text not in out:
                out.append(text)
        return out
    if isinstance(value, tuple):
        return _normalize_blockers(list(value))
    text = _normalize_text(value)
    if not text:
        return []
    if "," in text:
        return _normalize_blockers([part.strip() for part in text.split(",")])
    return [text]


def _normalize_decision_explain(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _derive_blockers(payload: dict[str, Any]) -> list[str]:
    categorized: list[str] = []
    for field in _LIST_FIELDS:
        for candidate in _normalize_blockers(payload.get(field)):
            if candidate not in categorized:
                categorized.append(candidate)
    if categorized:
        return categorized
    blockers = _normalize_blockers(payload.get("blockers"))
    if blockers:
        return blockers
    for candidate in _normalize_blockers(payload.get("tradable_reasons_blocking")):
        if candidate not in blockers:
            blockers.append(candidate)
    for field in ("final_blocker", "hard_reason"):
        text = _normalize_text(payload.get(field))
        if text and text not in blockers:
            blockers.append(text)
    legacy_issue = str(payload.get("validation_issue_code") or payload.get("entry_status") or "").strip().upper()
    if legacy_issue and legacy_issue not in _LEGACY_NON_ERROR_ENTRY_STATUSES and legacy_issue.lower() not in ENTRY_STATUSES and legacy_issue not in blockers:
        blockers.append(legacy_issue)
    entry_status = str(payload.get("entry_status") or "").strip().upper()
    if (
        entry_status
        and entry_status not in _LEGACY_NON_ERROR_ENTRY_STATUSES
        and entry_status.lower() not in ENTRY_STATUSES
        and entry_status not in blockers
    ):
        blockers.append(entry_status)
    return blockers


def _derive_execution_status(payload: dict[str, Any], readiness: str, hard_blockers: list[str]) -> str:
    existing = _normalize_text(payload.get("execution_status"))
    if existing:
        return str(existing).strip().lower()
    if hard_blockers:
        return "blocked"
    permission = str(payload.get("permission") or "").strip().upper()
    final_action = str(payload.get("final_action") or "").strip().upper()
    if permission == "EXECUTE" and final_action == "EXECUTE" and readiness == "READY":
        return "executable"
    if permission == "QUEUE_ONLY" and final_action == "QUEUE_ONLY" and readiness == "QUEUE_ONLY":
        return "queue_only"
    return "advisory_only"


def _derive_readiness(payload: dict[str, Any], blockers: list[str]) -> str:
    existing = _normalize_text(payload.get("readiness"))
    if existing:
        return str(existing).upper()
    permission = str(payload.get("permission") or "").strip().upper()
    final_action = str(payload.get("final_action") or "").strip().upper()
    status = str(payload.get("status") or "").strip().upper()
    if status in {"BLOCKED_CONTRACT", "BLOCKED_APPROVAL", "INVALID"} or permission == "BLOCK" or final_action == "BLOCK":
        return "BLOCKED"
    if permission == "EXECUTE" or final_action == "EXECUTE":
        return "READY"
    if permission == "QUEUE_ONLY" or final_action == "QUEUE_ONLY":
        return "QUEUE_ONLY"
    if blockers and permission not in {"ADVISORY_ONLY", "QUEUE_ONLY", "EXECUTE"}:
        return "BLOCKED"
    return "ADVISORY_ONLY"


def _derive_quote_source(payload: dict[str, Any]) -> str:
    for field in ("quote_source", "option_ltp_source"):
        text = _normalize_text(payload.get(field))
        if text:
            return str(text).lower()
    return "unknown"


def _derive_timestamp(payload: dict[str, Any]) -> str | None:
    for field in ("timestamp", "last_seen_ts", "timestamp_utc_iso", "last_seen", "created_at"):
        text = _normalize_text(payload.get(field))
        if text:
            return text
    return None


def _legacy_entry_state(payload: dict[str, Any]) -> dict[str, Any]:
    canonical_fields_present = any(
        key in payload
        for key in (
            "execution_entry",
            "execution_entry_source",
            "execution_entry_status",
            "display_entry",
            "display_entry_source",
            "display_entry_status",
            "entry_reason",
            "entry_clear_reason",
        )
    )
    if canonical_fields_present:
        execution_entry = _safe_float(payload.get("execution_entry"))
        execution_entry_source = _safe_lower_text(payload.get("execution_entry_source")) or "none"
        execution_entry_status = _safe_lower_text(payload.get("execution_entry_status")) or "missing"
        display_entry = _safe_float(payload.get("display_entry"))
        display_entry_source = _safe_lower_text(payload.get("display_entry_source")) or "none"
        display_entry_status = _safe_lower_text(payload.get("display_entry_status")) or "missing"
        return {
            "execution_entry": execution_entry,
            "execution_entry_source": execution_entry_source,
            "execution_entry_status": execution_entry_status,
            "display_entry": display_entry,
            "display_entry_source": display_entry_source,
            "display_entry_status": display_entry_status,
            "entry_reason": _normalize_text(payload.get("entry_reason")),
            "entry_clear_reason": _normalize_text(payload.get("entry_clear_reason")),
            "entry": display_entry,
            "entry_status": display_entry_status,
            "entry_source": display_entry_source,
            "display_max_age_sec": _safe_float(payload.get("display_max_age_sec")),
            "execution_max_age_sec": _safe_float(payload.get("execution_max_age_sec")),
        }
    quote_age_sec = _safe_float(payload.get("quote_age_sec"))
    if quote_age_sec is None:
        quote_age_sec = _safe_float(payload.get("price_age_sec"))
    quote_source = _derive_quote_source(payload)
    validation_issue_code = str(payload.get("validation_issue_code") or "").strip().upper()
    if not validation_issue_code:
        legacy_status = str(payload.get("entry_status") or "").strip().upper()
        if legacy_status and legacy_status not in _LEGACY_NON_ERROR_ENTRY_STATUSES and legacy_status.lower() not in ENTRY_STATUSES:
            validation_issue_code = legacy_status
    try:
        state = build_entry_state(
            symbol=payload.get("symbol"),
            expiry=payload.get("expiry_date") or payload.get("expiry"),
            strike=payload.get("strike"),
            right=payload.get("option_type") or payload.get("type") or payload.get("right"),
            side=payload.get("side"),
            direction=payload.get("direction"),
            bid=payload.get("best_bid") or payload.get("bid") or payload.get("opt_bid"),
            ask=payload.get("best_ask") or payload.get("ask") or payload.get("opt_ask"),
            mark=payload.get("mark_price"),
            mid=payload.get("mid_price"),
            last=payload.get("current_ltp") or payload.get("suggested_entry") or payload.get("opt_ltp") or payload.get("ltp"),
            quote_age_sec=quote_age_sec,
            mode=payload.get("execution_mode") or payload.get("mode"),
            allow_stale_quotes=str(payload.get("execution_mode") or payload.get("mode") or "").strip().upper() in {"PAPER", "SIM", "ADVISORY", "PLANNING", "OFFHOURS"},
            market_open=str(payload.get("execution_mode") or payload.get("mode") or "").strip().upper() not in {"OFFHOURS", "ADVISORY", "PLANNING"},
            instrument_matches=not bool(payload.get("unresolved_contract")),
            quote_source=quote_source,
        )
    except EntryContractViolation as exc:
        raise AdvisorySchemaError(str(exc)) from exc
    if validation_issue_code and state.get("display_entry") is None and not state.get("entry_clear_reason"):
        state["entry_clear_reason"] = str(validation_issue_code).lower()
    return state


def _looks_like_canonical(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    return all(field in payload for field in REQUIRED_FIELDS)


def _legacy_adapter(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out.setdefault("trade_id", payload.get("trade_id") or payload.get("advisory_id") or payload.get("trade_key"))
    out.setdefault("advisory_id", payload.get("advisory_id") or payload.get("trade_id") or payload.get("trade_key"))
    out.setdefault(
        "strategy_id",
        derive_strategy_id(
            payload.get("strategy_id"),
            payload.get("strategy_name") or payload.get("strategy") or payload.get("generator"),
        ),
    )
    out.setdefault(
        "strategy_name",
        payload.get("strategy_name") or payload.get("strategy") or payload.get("generator") or payload.get("strategy_id"),
    )
    out.setdefault("timestamp", _derive_timestamp(payload))
    out.setdefault("instrument_type", payload.get("instrument_type") or payload.get("instrument"))
    out.setdefault("decision_explain", _normalize_decision_explain(payload.get("decision_explain")))
    market_open = _normalize_bool(payload.get("market_open"))
    if market_open is None:
        market_context = payload.get("market_context")
        if isinstance(market_context, dict):
            market_open = _normalize_bool(market_context.get("market_open"))
    if market_open is None:
        market_open = _normalize_bool(payload.get("freshness_market_open"))
    if market_open is None:
        market_open = str(payload.get("execution_mode") or payload.get("mode") or "").strip().upper() not in {"OFFHOURS", "PAPER", "BACKTEST"}
    out.setdefault("market_open", market_open)
    lifecycle = _legacy_entry_state(payload)
    out.update(lifecycle)
    out["entry"] = lifecycle.get("display_entry")
    out["entry_status"] = lifecycle.get("display_entry_status") or "missing"
    out["entry_source"] = lifecycle.get("display_entry_source")
    out["blockers"] = _derive_blockers(payload)
    out["hard_blockers"] = _normalize_blockers(payload.get("hard_blockers"))
    out["soft_penalties"] = _normalize_blockers(payload.get("soft_penalties"))
    out["warnings"] = _normalize_blockers(payload.get("warnings"))
    if not out["hard_blockers"] and not out["soft_penalties"] and not out["warnings"]:
        ctx = {
            "mode": payload.get("execution_mode") or payload.get("mode"),
            "market_open": str(payload.get("execution_mode") or payload.get("mode") or "").strip().upper() not in {"OFFHOURS", "ADVISORY", "PLANNING"},
            "allow_stale_quotes": bool(payload.get("allow_stale_quotes")),
            "permission": payload.get("permission"),
            "entry_status": payload.get("entry_status"),
            "subscription_failed": bool(payload.get("subscription_failed")),
            "quote_source": payload.get("quote_source") or payload.get("option_ltp_source"),
            "quote_age_sec": payload.get("quote_age_sec") if payload.get("quote_age_sec") not in (None, "", "None") else payload.get("price_age_sec"),
            "current_ltp": payload.get("current_ltp"),
            "reference_price": payload.get("validation_reference_price") or payload.get("entry_price") or payload.get("expected_entry"),
            "advisory_id": payload.get("advisory_id") or payload.get("trade_id") or payload.get("trade_key"),
            "symbol": payload.get("symbol"),
            "best_bid": payload.get("best_bid") or payload.get("bid") or payload.get("opt_bid"),
            "best_ask": payload.get("best_ask") or payload.get("ask") or payload.get("opt_ask"),
        }
        for code in out["blockers"]:
            decision = classify_issue(code, ctx)
            if decision.category == ISSUE_CATEGORY_HARD:
                out["hard_blockers"].append(code)
            elif decision.category == ISSUE_CATEGORY_SOFT:
                out["soft_penalties"].append(code)
            elif decision.category == ISSUE_CATEGORY_WARNING:
                out["warnings"].append(code)
        out["hard_blockers"] = _normalize_blockers(out["hard_blockers"])
        out["soft_penalties"] = _normalize_blockers(out["soft_penalties"])
        out["warnings"] = _normalize_blockers(out["warnings"])
    out["readiness"] = _derive_readiness(payload, out["hard_blockers"])
    out["quote_source"] = _derive_quote_source(payload)
    if out.get("quote_age_sec") in (None, "", "None"):
        out["quote_age_sec"] = _safe_float(payload.get("price_age_sec"))
    if out.get("confidence") in (None, "", "None"):
        out["confidence"] = _safe_float(payload.get("global_confidence"))
    out.setdefault("confidence_raw", _safe_float(payload.get("confidence_raw")))
    if out.get("confidence_raw") in (None, "", "None"):
        out["confidence_raw"] = _safe_float(out.get("confidence"))
    out.setdefault("confidence_model_raw", _safe_float(payload.get("confidence_model_raw")))
    out.setdefault("confidence_model_component", _safe_float(payload.get("confidence_model_component")))
    out.setdefault("confidence_micro_component", _safe_float(payload.get("confidence_micro_component")))
    out.setdefault("confidence_micro_blend_method", _normalize_text(payload.get("confidence_micro_blend_method")))
    out.setdefault("confidence_after_micro", _safe_float(payload.get("confidence_after_micro")))
    out.setdefault("confidence_after_alpha", _safe_float(payload.get("confidence_after_alpha")))
    out.setdefault("confidence_after_latency", _safe_float(payload.get("confidence_after_latency")))
    out.setdefault("confidence_before_soft_veto", _safe_float(payload.get("confidence_before_soft_veto")))
    out.setdefault("confidence_after_soft_veto", _safe_float(payload.get("confidence_after_soft_veto")))
    out.setdefault("confidence_penalty_soft_veto_total", _safe_float(payload.get("confidence_penalty_soft_veto_total")))
    out.setdefault(
        "confidence_penalty_soft_veto_reasons",
        _normalize_blockers(payload.get("confidence_penalty_soft_veto_reasons")),
    )
    out.setdefault("confidence_gate_threshold", _safe_float(payload.get("confidence_gate_threshold")))
    out.setdefault("confidence_raw_gate_threshold", _safe_float(payload.get("confidence_raw_gate_threshold")))
    out.setdefault("confidence_final_gate_threshold", _safe_float(payload.get("confidence_final_gate_threshold")))
    out.setdefault("confidence_rejection_stage", _normalize_text(payload.get("confidence_rejection_stage")))
    out.setdefault("confidence_penalty", _safe_float(payload.get("confidence_penalty")) or 0.0)
    out.setdefault("confidence_final", _safe_float(payload.get("confidence_final")))
    if out.get("confidence_final") in (None, "", "None"):
        out["confidence_final"] = _safe_float(out.get("confidence"))
    out.setdefault("advisory_visible", bool(payload.get("advisory_visible", True)))
    out.setdefault("is_executable", bool(payload.get("is_executable", False)))
    out.setdefault("entry_source", payload.get("entry_source") or payload.get("entry_price_source") or payload.get("quote_source"))
    out["execution_status"] = _derive_execution_status(payload, out["readiness"], out["hard_blockers"])
    out.setdefault("validation_issue_code", payload.get("validation_issue_code"))
    return out


def validate_advisory_row(payload: dict[str, Any], *, allow_legacy: bool = False) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AdvisorySchemaError("advisory row must be a dict")
    out = _legacy_adapter(payload) if allow_legacy and not _looks_like_canonical(payload) else dict(payload)
    for field in REQUIRED_FIELDS:
        if field not in out:
            raise AdvisorySchemaError(f"missing required field: {field}")

    trade_id = _normalize_text(out.get("trade_id"))
    strategy_id = _normalize_text(out.get("strategy_id"))
    advisory_id = _normalize_text(out.get("advisory_id"))
    symbol = _normalize_text(out.get("symbol"))
    strategy_name = _normalize_text(out.get("strategy_name"))
    timestamp = _normalize_text(out.get("timestamp"))
    instrument_type = _normalize_text(out.get("instrument_type"))
    execution_entry = _safe_float(out.get("execution_entry"))
    execution_entry_source = _safe_lower_text(out.get("execution_entry_source")) or "none"
    execution_entry_status = str(out.get("execution_entry_status") or "").strip().lower()
    display_entry = _safe_float(out.get("display_entry"))
    display_entry_source = _safe_lower_text(out.get("display_entry_source")) or "none"
    display_entry_status = str(out.get("display_entry_status") or "").strip().lower()
    entry_reason = _normalize_text(out.get("entry_reason"))
    entry_clear_reason = _normalize_text(out.get("entry_clear_reason"))
    entry_status = str(out.get("entry_status") or "").strip().lower()
    readiness = str(out.get("readiness") or "").strip().upper()
    quote_source = str(out.get("quote_source") or "").strip().lower()
    blockers = _normalize_blockers(out.get("blockers"))
    hard_blockers = _normalize_blockers(out.get("hard_blockers"))
    soft_penalties = _normalize_blockers(out.get("soft_penalties"))
    warnings = _normalize_blockers(out.get("warnings"))
    confidence = _safe_float(out.get("confidence"))
    confidence_raw = _safe_float(out.get("confidence_raw"))
    confidence_model_raw = _safe_float(out.get("confidence_model_raw"))
    confidence_model_component = _safe_float(out.get("confidence_model_component"))
    confidence_micro_component = _safe_float(out.get("confidence_micro_component"))
    confidence_micro_blend_method = _normalize_text(out.get("confidence_micro_blend_method"))
    confidence_after_micro = _safe_float(out.get("confidence_after_micro"))
    confidence_after_alpha = _safe_float(out.get("confidence_after_alpha"))
    confidence_after_latency = _safe_float(out.get("confidence_after_latency"))
    confidence_before_soft_veto = _safe_float(out.get("confidence_before_soft_veto"))
    confidence_after_soft_veto = _safe_float(out.get("confidence_after_soft_veto"))
    confidence_penalty_soft_veto_total = _safe_float(out.get("confidence_penalty_soft_veto_total"))
    confidence_penalty_soft_veto_reasons = _normalize_blockers(out.get("confidence_penalty_soft_veto_reasons"))
    confidence_gate_threshold = _safe_float(out.get("confidence_gate_threshold"))
    confidence_raw_gate_threshold = _safe_float(out.get("confidence_raw_gate_threshold"))
    confidence_final_gate_threshold = _safe_float(out.get("confidence_final_gate_threshold"))
    confidence_rejection_stage = _normalize_text(out.get("confidence_rejection_stage"))
    confidence_penalty = _safe_float(out.get("confidence_penalty"))
    confidence_final = _safe_float(out.get("confidence_final"))
    threshold_display = _safe_float(out.get("threshold_display"))
    threshold_advisory = _safe_float(out.get("threshold_advisory"))
    threshold_execution = _safe_float(out.get("threshold_execution"))
    confidence_vs_threshold_reason = _normalize_text(out.get("confidence_vs_threshold_reason"))
    quote_age_sec = _safe_float(out.get("quote_age_sec"))
    entry = _safe_float(out.get("entry"))
    execution_status = str(out.get("execution_status") or "").strip().lower()
    entry_source = _normalize_text(out.get("entry_source"))
    advisory_visible = bool(out.get("advisory_visible", True))
    is_executable = bool(out.get("is_executable", False))
    decision_explain = _normalize_decision_explain(out.get("decision_explain"))
    market_open = _normalize_bool(out.get("market_open"))

    categorized_union = []
    for source in (hard_blockers, soft_penalties, warnings):
        for code in source:
            if code not in categorized_union:
                categorized_union.append(code)
    if categorized_union:
        blockers = categorized_union

    if not trade_id:
        raise AdvisorySchemaError("trade_id must be non-empty")
    if not strategy_id:
        raise AdvisorySchemaError("strategy_id must be non-empty")
    if not advisory_id:
        raise AdvisorySchemaError("advisory_id must be non-empty")
    if not symbol:
        raise AdvisorySchemaError("symbol must be non-empty")
    if not strategy_name:
        raise AdvisorySchemaError("strategy_name must be non-empty")
    if not timestamp:
        raise AdvisorySchemaError("timestamp must be non-empty")
    if not instrument_type:
        raise AdvisorySchemaError("instrument_type must be non-empty")
    if execution_entry_status not in EXECUTION_ENTRY_STATUSES:
        raise AdvisorySchemaError(f"invalid execution_entry_status: {execution_entry_status}")
    if display_entry_status not in DISPLAY_ENTRY_STATUSES:
        raise AdvisorySchemaError(f"invalid display_entry_status: {display_entry_status}")
    if entry_status not in ENTRY_STATUSES:
        raise AdvisorySchemaError(f"invalid entry_status: {entry_status}")
    if readiness not in READINESS_STATES:
        raise AdvisorySchemaError(f"invalid readiness: {readiness}")
    if execution_status not in EXECUTION_STATUSES:
        raise AdvisorySchemaError(f"invalid execution_status: {execution_status}")
    if execution_entry_source not in ENTRY_SOURCE_ENUM:
        raise AdvisorySchemaError(f"invalid execution_entry_source: {execution_entry_source}")
    if display_entry_source not in ENTRY_SOURCE_ENUM:
        raise AdvisorySchemaError(f"invalid display_entry_source: {display_entry_source}")
    if quote_source not in QUOTE_SOURCES:
        raise AdvisorySchemaError(f"invalid quote_source: {quote_source}")
    if confidence is not None and not (0.0 <= confidence <= 1.0):
        raise AdvisorySchemaError("confidence must be within [0.0, 1.0]")
    if confidence_raw is not None and not (0.0 <= confidence_raw <= 1.0):
        raise AdvisorySchemaError("confidence_raw must be within [0.0, 1.0]")
    for field_name, value in (
        ("confidence_model_raw", confidence_model_raw),
        ("confidence_model_component", confidence_model_component),
        ("confidence_micro_component", confidence_micro_component),
        ("confidence_after_micro", confidence_after_micro),
        ("confidence_after_alpha", confidence_after_alpha),
        ("confidence_after_latency", confidence_after_latency),
        ("confidence_before_soft_veto", confidence_before_soft_veto),
        ("confidence_after_soft_veto", confidence_after_soft_veto),
        ("confidence_penalty_soft_veto_total", confidence_penalty_soft_veto_total),
        ("confidence_gate_threshold", confidence_gate_threshold),
        ("confidence_raw_gate_threshold", confidence_raw_gate_threshold),
        ("confidence_final_gate_threshold", confidence_final_gate_threshold),
    ):
        if value is not None and not (0.0 <= value <= 1.0):
            raise AdvisorySchemaError(f"{field_name} must be within [0.0, 1.0]")
    if confidence_penalty is not None and confidence_penalty < 0.0:
        raise AdvisorySchemaError("confidence_penalty must be non-negative")
    if confidence_final is not None and not (0.0 <= confidence_final <= 1.0):
        raise AdvisorySchemaError("confidence_final must be within [0.0, 1.0]")
    for field_name, value in (
        ("threshold_display", threshold_display),
        ("threshold_advisory", threshold_advisory),
        ("threshold_execution", threshold_execution),
    ):
        if value is not None and not (0.0 <= value <= 1.0):
            raise AdvisorySchemaError(f"{field_name} must be within [0.0, 1.0]")
    if (
        threshold_display is not None
        and threshold_advisory is not None
        and threshold_display > threshold_advisory
    ):
        raise AdvisorySchemaError("threshold_display cannot exceed threshold_advisory")
    if (
        threshold_advisory is not None
        and threshold_execution is not None
        and threshold_advisory > threshold_execution
    ):
        raise AdvisorySchemaError("threshold_advisory cannot exceed threshold_execution")
    if quote_age_sec is not None and quote_age_sec < 0.0:
        raise AdvisorySchemaError("quote_age_sec must be non-negative")
    if market_open is None:
        raise AdvisorySchemaError("market_open must be explicitly boolean")
    if not isinstance(decision_explain, list):
        raise AdvisorySchemaError("decision_explain must be a list")
    if quote_age_sec is not None and not quote_source:
        raise AdvisorySchemaError("quote_age_sec requires quote_source")
    if execution_entry is not None and execution_entry_status != "executable":
        raise AdvisorySchemaError("execution_entry requires execution_entry_status=executable")
    if execution_entry is None and execution_entry_status == "executable":
        raise AdvisorySchemaError("execution_entry_status=executable requires execution_entry")
    if display_entry is not None and display_entry_status == "missing":
        raise AdvisorySchemaError("display_entry requires non-missing display_entry_status")
    if display_entry is None and display_entry_status != "missing":
        raise AdvisorySchemaError("missing display_entry requires display_entry_status=missing")
    if display_entry is None and not entry_clear_reason:
        raise AdvisorySchemaError("missing display_entry requires entry_clear_reason")
    if display_entry is not None and not display_entry_source:
        raise AdvisorySchemaError("display_entry requires display_entry_source")
    if execution_entry is not None and not execution_entry_source:
        raise AdvisorySchemaError("execution_entry requires execution_entry_source")
    if readiness == "READY" and hard_blockers:
        raise AdvisorySchemaError("readiness=READY cannot coexist with blockers")
    if readiness == "BLOCKED" and not hard_blockers:
        raise AdvisorySchemaError("readiness=BLOCKED requires hard_blockers")
    if execution_status == "blocked" and not hard_blockers:
        raise AdvisorySchemaError("execution_status=blocked requires hard_blockers")
    if is_executable and execution_status != "executable":
        raise AdvisorySchemaError("is_executable requires execution_status=executable")
    if entry != display_entry:
        raise AdvisorySchemaError("entry must equal display_entry")
    if entry_status.lower() != display_entry_status:
        raise AdvisorySchemaError("entry_status must equal display_entry_status")
    if entry is not None and entry_status == "missing":
        raise AdvisorySchemaError("non-null entry cannot have entry_status=missing")
    if entry is None and entry_status != "missing":
        raise AdvisorySchemaError("missing entry requires entry_status=missing")

    out["trade_id"] = trade_id
    out["strategy_id"] = strategy_id
    out["advisory_id"] = advisory_id
    out["symbol"] = symbol
    out["strategy_name"] = strategy_name
    out["timestamp"] = timestamp
    out["instrument_type"] = instrument_type.upper()
    out["execution_entry"] = execution_entry
    out["execution_entry_source"] = execution_entry_source
    out["execution_entry_status"] = execution_entry_status
    out["display_entry"] = display_entry
    out["display_entry_source"] = display_entry_source
    out["display_entry_status"] = display_entry_status
    out["entry_reason"] = entry_reason
    out["entry_clear_reason"] = entry_clear_reason
    out["entry"] = entry
    out["entry_status"] = display_entry_status
    out["confidence"] = confidence
    out["confidence_raw"] = confidence_raw
    out["confidence_model_raw"] = confidence_model_raw
    out["confidence_model_component"] = confidence_model_component
    out["confidence_micro_component"] = confidence_micro_component
    out["confidence_micro_blend_method"] = confidence_micro_blend_method
    out["confidence_after_micro"] = confidence_after_micro
    out["confidence_after_alpha"] = confidence_after_alpha
    out["confidence_after_latency"] = confidence_after_latency
    out["confidence_before_soft_veto"] = confidence_before_soft_veto
    out["confidence_after_soft_veto"] = confidence_after_soft_veto
    out["confidence_penalty_soft_veto_total"] = confidence_penalty_soft_veto_total
    out["confidence_penalty_soft_veto_reasons"] = confidence_penalty_soft_veto_reasons
    out["confidence_gate_threshold"] = confidence_gate_threshold
    out["confidence_raw_gate_threshold"] = confidence_raw_gate_threshold
    out["confidence_final_gate_threshold"] = confidence_final_gate_threshold
    out["confidence_rejection_stage"] = confidence_rejection_stage
    out["confidence_penalty"] = float(confidence_penalty or 0.0)
    out["confidence_final"] = confidence_final
    out["threshold_display"] = threshold_display
    out["threshold_advisory"] = threshold_advisory
    out["threshold_execution"] = threshold_execution
    out["confidence_vs_threshold_reason"] = confidence_vs_threshold_reason
    out["readiness"] = readiness
    out["hard_blockers"] = hard_blockers
    out["soft_penalties"] = soft_penalties
    out["warnings"] = warnings
    out["blockers"] = blockers
    out["execution_status"] = execution_status
    out["advisory_visible"] = advisory_visible
    out["is_executable"] = is_executable
    out["entry_source"] = display_entry_source
    out["quote_source"] = quote_source
    out["quote_age_sec"] = quote_age_sec
    out["decision_explain"] = decision_explain
    out["market_open"] = market_open
    return out


def serialize_advisory_row(payload: dict[str, Any], *, allow_legacy: bool = False) -> dict[str, Any]:
    return validate_advisory_row(payload, allow_legacy=allow_legacy)


def deserialize_advisory_row(payload: dict[str, Any], *, allow_legacy: bool = False) -> dict[str, Any]:
    return validate_advisory_row(payload, allow_legacy=allow_legacy)
