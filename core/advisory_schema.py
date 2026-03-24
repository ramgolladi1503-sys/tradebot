from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.entry_semantics import (
    DISPLAY_ENTRY_STATUSES,
    ENTRY_SOURCE_ENUM,
    EXECUTION_ENTRY_STATUSES,
    EntryContractViolation,
    build_entry_state,
    derive_execution_entry_recovery,
    should_allow_last_execution_fallback,
)
from core.execution_entry_trace import append_execution_entry_trace
from core.issue_policy import (
    ISSUE_CATEGORY_HARD,
    ISSUE_CATEGORY_SOFT,
    ISSUE_CATEGORY_WARNING,
    classify_issue,
)
from core.advisory_row_integrity import (
    ADVISORY_ONLY_ROW_KIND,
    BLOCKED_DEBUG_ROW_KIND,
    CANONICAL_ROW_KIND,
    log_corrupt_advisory_row,
    validate_price_level_invariants,
)
from core.paths import logs_dir
from core.time_utils import (
    coerce_ts_epoch as _normalize_ts_epoch,
    format_ts_ist as _format_ts_ist,
    ist_iso_from_epoch as _ist_iso_from_epoch,
    utc_iso_from_epoch as _utc_iso_from_epoch,
)
from core.trade_identity import derive_strategy_id, infer_candidate_identity
from core.trade_state_machine import TRADE_LIFECYCLE_STATES

try:
    from config import config as cfg
except Exception:
    cfg = None


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
_OPTION_SIDE_RE = re.compile(r"(?:^|[^A-Z0-9])(CE|PE)(?:$|[^A-Z0-9])")
_LIST_FIELDS = ("hard_blockers", "soft_penalties", "warnings")
_EXECUTABLE_ENTRY_SOURCES = {"ask", "bid", "last", "retained_prior_ask", "retained_prior_bid"}
_IST = timezone(timedelta(hours=5, minutes=30))
_STALE_QUOTE_AGE_SENTINEL = float(10**9)


def _strict_level_invariants_enabled() -> bool:
    try:
        return bool(getattr(cfg, "ADVISORY_SCHEMA_STRICT_LEVEL_INVARIANTS", True))
    except Exception:
        return True


def _candidate_row_corruption_log_enabled() -> bool:
    try:
        return bool(getattr(cfg, "CANDIDATE_ROW_CORRUPTION_LOG_ENABLE", True))
    except Exception:
        return True


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


def _normalize_quote_age_value(value: Any) -> float | None:
    age = _safe_float(value)
    if age is None:
        return None
    if age < 0.0:
        return None
    if float(age) >= _STALE_QUOTE_AGE_SENTINEL:
        return None
    return float(age)


def _canonical_quote_age_sec(payload: dict[str, Any]) -> float | None:
    if not isinstance(payload, dict):
        return None
    for field in ("quote_age_sec", "option_age_sec", "price_age_sec", "option_ltp_age_sec"):
        age = _normalize_quote_age_value(payload.get(field))
        if age is not None:
            return age
    return None


def _parse_datetime_text(value: Any) -> datetime | None:
    text = _normalize_text(value)
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(normalized)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _coerce_ts_epoch(value: Any) -> float | None:
    return _normalize_ts_epoch(value)


def _utc_timestamp_from_epoch(ts_epoch: float) -> str:
    return _utc_iso_from_epoch(ts_epoch)


def _ist_timestamp_from_epoch(ts_epoch: float) -> str:
    return _ist_iso_from_epoch(ts_epoch)


def _ist_display_timestamp_from_epoch(ts_epoch: float) -> str:
    val = _format_ts_ist(ts_epoch)
    if val:
        return val
    return "INVALID_TS"


def _normalize_option_type(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if text in {"CE", "CALL", "C"}:
        return "CE"
    if text in {"PE", "PUT", "P"}:
        return "PE"
    return None


def _parse_option_type(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if text.endswith("CE"):
        return "CE"
    if text.endswith("PE"):
        return "PE"
    match = _OPTION_SIDE_RE.search(text)
    if match:
        return match.group(1)
    return None


def _normalize_instrument_type(value: Any) -> str:
    text = (_normalize_text(value) or "").upper()
    if not text:
        return ""
    if text in {"OPT", "OPTION", "OPTIONS", "OPTIDX", "OPTSTK", "CE", "PE", "CALL", "PUT"}:
        return "OPT"
    if text in {"EQ", "STK", "STOCK"}:
        return "EQ"
    if text in {"FUT", "FUTURE", "FUTURES"}:
        return "FUT"
    if text in {"INDEX", "IDX"}:
        return "INDEX"
    return text


def _assume_opt_candidate_types() -> set[str]:
    raw = _normalize_text(getattr(cfg, "ADVISORY_INSTRUMENT_TYPE_ASSUME_OPT_CANDIDATE_TYPES", "")) if cfg else ""
    if not raw:
        return set()
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _instrument_type_fallback() -> str:
    fallback = _normalize_text(getattr(cfg, "ADVISORY_INSTRUMENT_TYPE_FALLBACK", "UNKNOWN")) if cfg else "UNKNOWN"
    return fallback.upper() if fallback else "UNKNOWN"


def _infer_instrument_type(payload: dict[str, Any]) -> tuple[str, str]:
    explicit = _normalize_instrument_type(payload.get("instrument_type") or payload.get("instrument"))
    if explicit:
        return explicit, "explicit"
    option_type = (
        _normalize_option_type(payload.get("option_type"))
        or _normalize_option_type(payload.get("type"))
        or _normalize_option_type(payload.get("right"))
        or _parse_option_type(payload.get("tradingsymbol"))
        or _parse_option_type(payload.get("instrument_id"))
    )
    if option_type:
        return "OPT", "option_type"
    candidate_type = (_normalize_text(payload.get("candidate_type")) or "").lower()
    if candidate_type and candidate_type in _assume_opt_candidate_types():
        return "OPT", "candidate_type"
    return _instrument_type_fallback(), "fallback"


def _normalize_option_identity(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    instrument_type = _normalize_text(out.get("instrument_type") or out.get("instrument"))
    option_type = (
        _normalize_option_type(out.get("option_type"))
        or _normalize_option_type(out.get("type"))
        or _normalize_option_type(out.get("right"))
        or _parse_option_type(out.get("tradingsymbol"))
        or _parse_option_type(out.get("instrument_id"))
    )
    if instrument_type and instrument_type.upper() == "OPT" and option_type:
        out["option_type"] = option_type
        out["type"] = option_type
        out["right"] = option_type
    return out


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


def _has_executable_entry_truth(
    *,
    execution_entry: float | None,
    execution_entry_source: str | None,
    execution_entry_status: str | None,
) -> bool:
    return (
        execution_entry is not None
        and str(execution_entry_status or "").strip().lower() == "executable"
        and str(execution_entry_source or "").strip().lower() in _EXECUTABLE_ENTRY_SOURCES
    )


def _normalize_decision_explain(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _normalize_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _derive_candidate_status(payload: dict[str, Any]) -> str:
    existing = str(payload.get("candidate_status") or "").strip().lower()
    if existing in {"scored", "ranked", "advisory_only", "near_executable", "blocked", "blocked_contract", "executable"}:
        return existing
    status = str(payload.get("status") or "").strip().upper()
    hard_reason = str(payload.get("hard_reason") or "").strip().lower()
    permission_reason = str(payload.get("permission_reason") or "").strip().lower()
    if (
        bool(payload.get("unresolved_contract"))
        or status == "BLOCKED_CONTRACT"
        or hard_reason == "unresolved_contract"
        or permission_reason == "unresolved_contract"
    ):
        return "blocked_contract"
    if status in {"BLOCKED", "BLOCK"} or execution_status == "blocked" or permission in {"BLOCK"} or final_action in {"BLOCK"}:
        return "blocked"
    execution_entry = _safe_float(payload.get("execution_entry"))
    execution_entry_status = str(payload.get("execution_entry_status") or "").strip().lower()
    execution_status = str(payload.get("execution_status") or "").strip().lower()
    permission = str(payload.get("permission") or "").strip().upper()
    final_action = str(payload.get("final_action") or "").strip().upper()
    readiness = str(payload.get("readiness") or "").strip().upper()
    if (
        execution_entry is not None
        and execution_entry_status == "executable"
        and execution_status == "executable"
        and permission == "EXECUTE"
        and final_action == "EXECUTE"
        and readiness == "READY"
    ):
        return "executable"
    if (
        _safe_float(payload.get("rank_score")) is not None
        or _safe_float(payload.get("opportunity_score")) is not None
        or payload.get("opportunity_rank") not in (None, "", "None")
    ):
        if execution_status == "queue_only" or permission == "QUEUE_ONLY" or final_action == "QUEUE_ONLY" or readiness == "QUEUE_ONLY":
            return "near_executable"
        if execution_status in {"blocked", "advisory_only"} or permission in {"BLOCK", "ADVISORY_ONLY", "QUEUE_ONLY"}:
            return "advisory_only"
        return "ranked"
    if (
        _safe_float(payload.get("builder_confidence")) is not None
        or _safe_float(payload.get("confidence_raw")) is not None
        or bool(payload.get("score_breakdown"))
    ):
        if execution_status == "queue_only" or permission == "QUEUE_ONLY" or final_action == "QUEUE_ONLY" or readiness == "QUEUE_ONLY":
            return "near_executable"
        return "advisory_only" if execution_status in {"blocked", "advisory_only"} or permission in {"BLOCK", "ADVISORY_ONLY", "QUEUE_ONLY"} else "scored"
    return "scored"


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
    if _has_executable_entry_truth(
        execution_entry=_safe_float(payload.get("execution_entry")),
        execution_entry_source=_safe_lower_text(payload.get("execution_entry_source")) or "none",
        execution_entry_status=str(payload.get("execution_entry_status") or "").strip().lower(),
    ):
        return "executable"
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


_DECISION_TS_FIELDS = (
    "decision_ts_epoch",
    "decision_ts_utc",
    "decision_ts_ist",
    "ts_epoch",
    "ts_utc",
    "ts_ist",
    "timestamp_epoch_ms",
    "timestamp_utc_iso",
    "timestamp",
    "created_ts_epoch",
    "created_at",
)

_SNAPSHOT_TS_FIELDS = (
    "snapshot_ts_epoch",
    "snapshot_ts_utc",
    "snapshot_ts_ist",
    "quote_ts_epoch",
    "option_ltp_timestamp",
    "ltp_ts_epoch",
    "freshness_quote_epoch",
    "candle_ts_epoch",
    "last_candle_ts_epoch",
    "signal_candle_epoch",
)


def _select_ts_epoch(payload: dict[str, Any], fields: tuple[str, ...]) -> tuple[float | None, str | None]:
    if not isinstance(payload, dict):
        return None, None
    for field in fields:
        ts_epoch = _coerce_ts_epoch(payload.get(field))
        if ts_epoch is not None:
            return float(ts_epoch), field
    return None, None


def _derive_timestamp(payload: dict[str, Any]) -> str | None:
    ts_epoch, _ = _select_ts_epoch(payload, _DECISION_TS_FIELDS)
    if ts_epoch is not None:
        return _utc_timestamp_from_epoch(ts_epoch)
    return None


def _derive_ts_epoch(payload: dict[str, Any]) -> float | None:
    ts_epoch, _ = _select_ts_epoch(payload, _DECISION_TS_FIELDS)
    if ts_epoch is not None:
        return float(ts_epoch)
    ts_epoch, _ = _select_ts_epoch(payload, _SNAPSHOT_TS_FIELDS)
    if ts_epoch is not None:
        return float(ts_epoch)
    return None


def _apply_explicit_display_timestamps(payload: dict[str, Any], derived_ts_epoch: float) -> dict[str, Any]:
    out = dict(payload)
    existing_display_ts_epoch = _coerce_ts_epoch(out.get("display_ts_epoch"))
    existing_display_source = _normalize_text(out.get("display_ts_source"))
    existing_decision_ts_epoch = _coerce_ts_epoch(out.get("decision_ts_epoch"))
    existing_decision_source = _normalize_text(out.get("decision_ts_source"))
    existing_snapshot_ts_epoch = _coerce_ts_epoch(out.get("snapshot_ts_epoch"))
    existing_snapshot_source = _normalize_text(out.get("snapshot_ts_source"))

    if existing_decision_ts_epoch is not None:
        decision_ts_epoch = float(existing_decision_ts_epoch)
        decision_source = existing_decision_source or "preserved"
    else:
        decision_ts_epoch, decision_source = _select_ts_epoch(out, _DECISION_TS_FIELDS)

    if existing_snapshot_ts_epoch is not None:
        snapshot_ts_epoch = float(existing_snapshot_ts_epoch)
        snapshot_source = existing_snapshot_source or "preserved"
    else:
        snapshot_ts_epoch, snapshot_source = _select_ts_epoch(out, _SNAPSHOT_TS_FIELDS)

    if decision_ts_epoch is None and snapshot_ts_epoch is not None:
        decision_ts_epoch = float(snapshot_ts_epoch)
        decision_source = f"fallback:{snapshot_source}"
    if decision_ts_epoch is None:
        decision_ts_epoch = float(derived_ts_epoch)
        decision_source = "derived_ts_epoch"

    created_ts_epoch = _coerce_ts_epoch(out.get("created_ts_epoch"))
    if created_ts_epoch is None:
        created_ts_epoch = _coerce_ts_epoch(out.get("created_at"))
    if created_ts_epoch is None:
        created_ts_epoch = float(decision_ts_epoch)

    if existing_display_ts_epoch is not None:
        display_ts_epoch = float(existing_display_ts_epoch)
        display_source = existing_display_source or "preserved"
    else:
        display_ts_epoch = decision_ts_epoch if decision_ts_epoch is not None else snapshot_ts_epoch
        display_source = "decision_ts_epoch" if decision_ts_epoch is not None else "snapshot_ts_epoch"
        if decision_source and str(decision_source).startswith("fallback:"):
            display_source = "snapshot_ts_epoch"
        if display_ts_epoch is None:
            display_ts_epoch = float(derived_ts_epoch)
            display_source = "derived_ts_epoch"

    last_seen_ts_epoch = _coerce_ts_epoch(out.get("last_seen_ts_epoch"))
    if last_seen_ts_epoch is None:
        last_seen_ts_epoch = _coerce_ts_epoch(out.get("last_seen_ts"))
    if last_seen_ts_epoch is None:
        last_seen_ts_epoch = _coerce_ts_epoch(out.get("last_seen"))

    out["decision_ts_epoch"] = float(decision_ts_epoch)
    if not _normalize_text(out.get("decision_ts_utc")):
        out["decision_ts_utc"] = _utc_timestamp_from_epoch(decision_ts_epoch)
    if not _normalize_text(out.get("decision_ts_ist")):
        out["decision_ts_ist"] = _ist_timestamp_from_epoch(decision_ts_epoch)
    out["decision_ts_source"] = decision_source or out.get("decision_ts_source")

    out["snapshot_ts_epoch"] = float(snapshot_ts_epoch) if snapshot_ts_epoch is not None else None
    if snapshot_ts_epoch is not None:
        if not _normalize_text(out.get("snapshot_ts_utc")):
            out["snapshot_ts_utc"] = _utc_timestamp_from_epoch(snapshot_ts_epoch)
        if not _normalize_text(out.get("snapshot_ts_ist")):
            out["snapshot_ts_ist"] = _ist_timestamp_from_epoch(snapshot_ts_epoch)
    out["snapshot_ts_source"] = snapshot_source or out.get("snapshot_ts_source")

    out["display_ts_epoch"] = float(display_ts_epoch)
    if not _normalize_text(out.get("display_ts_utc")):
        out["display_ts_utc"] = _utc_timestamp_from_epoch(display_ts_epoch)
    if not _normalize_text(out.get("display_ts_ist")):
        out["display_ts_ist"] = _ist_display_timestamp_from_epoch(display_ts_epoch)
    out["display_ts_source"] = display_source or out.get("display_ts_source")

    out["created_ts_epoch"] = float(created_ts_epoch)
    if not _normalize_text(out.get("created_ts_utc")):
        out["created_ts_utc"] = _utc_timestamp_from_epoch(created_ts_epoch)
    if not _normalize_text(out.get("created_ts_ist")):
        out["created_ts_ist"] = _ist_timestamp_from_epoch(created_ts_epoch)

    out["last_seen_ts_epoch"] = float(last_seen_ts_epoch) if last_seen_ts_epoch is not None else None
    out["last_seen_ts_utc"] = _utc_timestamp_from_epoch(last_seen_ts_epoch) if last_seen_ts_epoch is not None else None
    out["last_seen_ts_ist"] = _ist_timestamp_from_epoch(last_seen_ts_epoch) if last_seen_ts_epoch is not None else None
    return out


def _derive_row_kind(payload: dict[str, Any]) -> str:
    explicit = _safe_lower_text(payload.get("row_kind"))
    if explicit:
        return explicit
    if str(payload.get("stage") or "").strip().lower() == "trade_builder":
        return BLOCKED_DEBUG_ROW_KIND
    if bool(payload.get("non_canonical_levels")):
        return ADVISORY_ONLY_ROW_KIND
    if not bool(payload.get("advisory_visible", True)):
        return ADVISORY_ONLY_ROW_KIND
    entry = _safe_float(payload.get("entry"))
    stop_loss = _safe_float(payload.get("stop_loss"))
    if stop_loss is None:
        stop_loss = _safe_float(payload.get("stop"))
    target = _safe_float(payload.get("target"))
    if entry is not None and stop_loss is not None and target is not None:
        return CANONICAL_ROW_KIND
    return ADVISORY_ONLY_ROW_KIND


def _has_timestamp_hint(payload: dict[str, Any]) -> bool:
    hint_fields = (
        _DECISION_TS_FIELDS
        + _SNAPSHOT_TS_FIELDS
        + ("last_seen_ts", "last_seen", "last_seen_ts_epoch")
    )
    return any(payload.get(field) not in (None, "", "None") for field in hint_fields)


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
            "entry_display_status": display_entry_status,
            "entry_reason": _normalize_text(payload.get("entry_reason")),
            "entry_clear_reason": _normalize_text(payload.get("entry_clear_reason")),
            "entry_block_code": _normalize_text(payload.get("entry_block_code"))
            or _normalize_text(payload.get("entry_clear_reason")),
            "entry": display_entry,
            "entry_status": display_entry_status,
            "entry_source": display_entry_source,
            "display_max_age_sec": _safe_float(payload.get("display_max_age_sec")),
            "execution_max_age_sec": _safe_float(payload.get("execution_max_age_sec")),
        }
    quote_age_sec = _canonical_quote_age_sec(payload)
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
            allow_last_execution=should_allow_last_execution_fallback(payload),
        )
    except EntryContractViolation as exc:
        raise AdvisorySchemaError(str(exc)) from exc
    if validation_issue_code and state.get("display_entry") is None and not state.get("entry_clear_reason"):
        state["entry_clear_reason"] = str(validation_issue_code).lower()
    append_execution_entry_trace(
        module="core.advisory_schema",
        stage="legacy_entry_state",
        row={
            "trade_id": payload.get("trade_id"),
            "symbol": payload.get("symbol"),
            "strategy": payload.get("strategy") or payload.get("strategy_name"),
            "entry": payload.get("entry"),
            "expected_entry": payload.get("expected_entry"),
            "current_ltp": payload.get("current_ltp"),
            "option_ltp_source": payload.get("option_ltp_source"),
            "quote_validation_status": payload.get("quote_validation_status"),
            "permission": payload.get("permission"),
            "execution_entry": state.get("execution_entry"),
            "execution_entry_status": state.get("execution_entry_status"),
            "execution_allowed": payload.get("execution_allowed"),
        },
        execution_entry_before=payload.get("execution_entry"),
        execution_entry_after=state.get("execution_entry"),
        execution_entry_status_before=payload.get("execution_entry_status"),
        execution_entry_status_after=state.get("execution_entry_status"),
        extra={
            "execution_entry_source": state.get("execution_entry_source"),
            "display_entry": state.get("display_entry"),
            "display_entry_status": state.get("display_entry_status"),
            "derivation_reason": state.get("_execution_entry_derivation_reason"),
            "derivation_source_chain": state.get("_execution_entry_derivation_source_chain"),
        },
    )
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
    identity = infer_candidate_identity(out)
    out.setdefault("candidate_type", identity.get("candidate_type") or "unknown")
    out.setdefault("strategy_family", identity.get("strategy_family") or "unknown")
    out.setdefault("setup_variant", identity.get("setup_variant") or "unknown")
    out.setdefault("direction", identity.get("direction") or "UNKNOWN")
    out.setdefault("candidate_status", _derive_candidate_status(out))
    out.setdefault("row_kind", _derive_row_kind(out))
    out.setdefault("non_canonical_levels", out.get("row_kind") != CANONICAL_ROW_KIND)
    out.setdefault("levels_recomputed_from_final_entry", bool(payload.get("levels_recomputed_from_final_entry", False)))
    out.setdefault("level_recompute_reason", _normalize_text(payload.get("level_recompute_reason")))
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
    out["entry_display_status"] = lifecycle.get("display_entry_status") or "missing"
    out["entry_block_code"] = _normalize_text(
        lifecycle.get("entry_block_code") or lifecycle.get("entry_clear_reason")
    )
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
        out["quote_age_sec"] = _canonical_quote_age_sec(payload)
    canonical_quote_age = _canonical_quote_age_sec(out)
    out["quote_age_sec"] = canonical_quote_age
    out["price_age_sec"] = canonical_quote_age
    out["option_age_sec"] = canonical_quote_age
    if out.get("confidence") in (None, "", "None"):
        out["confidence"] = _safe_float(payload.get("global_confidence"))
    out.setdefault("builder_confidence", _safe_float(payload.get("builder_confidence")))
    if out.get("builder_confidence") in (None, "", "None"):
        out["builder_confidence"] = _safe_float(payload.get("confidence_base"))
    if out.get("builder_confidence") in (None, "", "None"):
        out["builder_confidence"] = _safe_float(out.get("confidence"))
    out.setdefault("permission_confidence", _safe_float(payload.get("permission_confidence")))
    if out.get("permission_confidence") in (None, "", "None"):
        out["permission_confidence"] = _safe_float(payload.get("global_confidence"))
    out.setdefault("gating_base_confidence", _safe_float(payload.get("gating_base_confidence")))
    if out.get("gating_base_confidence") in (None, "", "None"):
        out["gating_base_confidence"] = _safe_float(payload.get("confidence_base"))
    out.setdefault("gating_final_confidence", _safe_float(payload.get("gating_final_confidence")))
    if out.get("gating_final_confidence") in (None, "", "None"):
        out["gating_final_confidence"] = _safe_float(payload.get("confidence_final"))
    out.setdefault("sizing_confluence_score", _safe_float(payload.get("sizing_confluence_score")))
    if out.get("sizing_confluence_score") in (None, "", "None"):
        detail = payload.get("trade_score_detail") or {}
        if isinstance(detail, dict):
            out["sizing_confluence_score"] = _safe_float(detail.get("confluence_score"))
    out.setdefault("sizing_reason", _normalize_text(payload.get("sizing_reason")))
    out.setdefault("ml_proba_input", _safe_float(payload.get("ml_proba_input")))
    out.setdefault("confluence_input", _safe_float(payload.get("confluence_input")))
    out.setdefault("ml_proba_source", _normalize_text(payload.get("ml_proba_source")))
    out.setdefault("confluence_source", _normalize_text(payload.get("confluence_source")))
    out.setdefault("confidence_size_multiplier", _safe_float(payload.get("confidence_size_multiplier")))
    out.setdefault("final_qty", _safe_float(payload.get("final_qty")))
    out.setdefault("rank_score", _safe_float(payload.get("rank_score")))
    out.setdefault("setup_strength", _safe_float(payload.get("setup_strength")))
    out.setdefault("regime_fit", _safe_float(payload.get("regime_fit")))
    out.setdefault("liquidity_score", _safe_float(payload.get("liquidity_score")))
    out.setdefault("spread_score", _safe_float(payload.get("spread_score")))
    out.setdefault("rr_score", _safe_float(payload.get("rr_score")))
    out.setdefault("timing_score", _safe_float(payload.get("timing_score")))
    out.setdefault("penalty_score", _safe_float(payload.get("penalty_score")))
    out.setdefault("score_breakdown", _normalize_mapping(payload.get("score_breakdown")))
    out.setdefault("penalty_reasons", _normalize_blockers(payload.get("penalty_reasons")))
    out.setdefault("score_inputs_used", _normalize_mapping(payload.get("score_inputs_used")))
    out.setdefault("opportunity_score", _safe_float(payload.get("opportunity_score")))
    try:
        opportunity_rank = payload.get("opportunity_rank")
        out.setdefault("opportunity_rank", int(opportunity_rank) if opportunity_rank not in (None, "", "None") else None)
    except Exception:
        out.setdefault("opportunity_rank", None)
    try:
        rank_global = payload.get("rank_global")
        out.setdefault("rank_global", int(rank_global) if rank_global not in (None, "", "None") else None)
    except Exception:
        out.setdefault("rank_global", None)
    try:
        rank_within_symbol = payload.get("rank_within_symbol")
        out.setdefault(
            "rank_within_symbol",
            int(rank_within_symbol) if rank_within_symbol not in (None, "", "None") else None,
        )
    except Exception:
        out.setdefault("rank_within_symbol", None)
    out.setdefault("opportunity_bucket", _normalize_text(payload.get("opportunity_bucket")))
    out.setdefault("selected_for_execution", _normalize_bool(payload.get("selected_for_execution")))
    out.setdefault("selection_reason", _normalize_text(payload.get("selection_reason")))
    out.setdefault("size_multiplier_reason", _normalize_text(payload.get("size_multiplier_reason")))
    out.setdefault("opportunity_size_multiplier", _safe_float(payload.get("opportunity_size_multiplier")))
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
    if out.get("gating_final_confidence") not in (None, "", "None"):
        out["confidence_final"] = _safe_float(out.get("gating_final_confidence"))
        out["confidence"] = _safe_float(out.get("gating_final_confidence"))
    out.setdefault("advisory_visible", bool(payload.get("advisory_visible", True)))
    out.setdefault("is_executable", bool(payload.get("is_executable", False)))
    out.setdefault("entry_source", payload.get("entry_source") or payload.get("entry_price_source") or payload.get("quote_source"))
    out["execution_status"] = _derive_execution_status(payload, out["readiness"], out["hard_blockers"])
    out.setdefault("validation_issue_code", payload.get("validation_issue_code"))
    out.setdefault("entry_display_status", _safe_lower_text(payload.get("entry_display_status")) or out.get("display_entry_status"))
    out.setdefault("entry_block_code", _normalize_text(payload.get("entry_block_code")) or _normalize_text(out.get("entry_clear_reason")))
    return out


def _apply_post_level_entry_mutation_policy(
    payload: dict[str, Any],
    *,
    entry_before: float | None,
    display_before: float | None,
    execution_before: float | None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    entry_after = _safe_float(out.get("entry"))
    display_after = _safe_float(out.get("display_entry"))
    execution_after = _safe_float(out.get("execution_entry"))
    entry_changed = (
        entry_before != entry_after
        or display_before != display_after
        or execution_before != execution_after
    )
    out["entry_changed_post_levels"] = bool(entry_changed)
    if not entry_changed:
        return out
    if _derive_row_kind(out) != CANONICAL_ROW_KIND:
        return out
    if _candidate_row_corruption_log_enabled():
        log_corrupt_advisory_row(out, "entry_changed_post_levels")
    if not _strict_level_invariants_enabled():
        return out
    out["row_kind"] = ADVISORY_ONLY_ROW_KIND
    out["non_canonical_levels"] = True
    out["levels_recomputed_from_final_entry"] = False
    out["level_recompute_reason"] = "entry_changed_post_levels"
    out["stop"] = None
    out["stop_loss"] = None
    out["stop_price"] = None
    out["original_stop"] = None
    out["current_stop"] = None
    out["target"] = None
    out["target_price"] = None
    return out


def _enforce_executable_entry_invariant(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    out = _normalize_option_identity(payload)
    entry_before = _safe_float(out.get("entry"))
    display_before = _safe_float(out.get("display_entry"))
    execution_before = _safe_float(out.get("execution_entry"))

    execution_entry = _safe_float(out.get("execution_entry"))
    execution_entry_source = _safe_lower_text(out.get("execution_entry_source")) or "none"
    execution_entry_status = str(out.get("execution_entry_status") or "").strip().lower()
    display_entry = _safe_float(out.get("display_entry"))
    display_entry_source = _safe_lower_text(out.get("display_entry_source")) or "none"
    display_entry_status = str(out.get("display_entry_status") or "").strip().lower()
    entry_display_status = str(out.get("entry_display_status") or display_entry_status or "").strip().lower()
    entry = _safe_float(out.get("entry"))
    entry_status = str(out.get("entry_status") or "").strip().lower()
    entry_block_code = _normalize_text(out.get("entry_block_code"))
    if execution_entry is None:
        recovery = derive_execution_entry_recovery(out)
        out["_execution_entry_derivation_reason"] = recovery.get("derivation_reason")
        out["_execution_entry_derivation_source_chain"] = list(recovery.get("derivation_source_chain") or [])
        recovered_entry = _safe_float(recovery.get("execution_entry"))
        recovered_status = str(recovery.get("execution_entry_status") or "").strip().lower()
        if recovered_entry is not None and recovered_status == "executable":
            out["execution_entry"] = recovered_entry
            out["execution_entry_source"] = _safe_lower_text(recovery.get("execution_entry_source")) or "none"
            out["execution_entry_status"] = "executable"
            execution_entry = recovered_entry
            execution_entry_source = _safe_lower_text(out.get("execution_entry_source")) or "none"
            execution_entry_status = "executable"
        elif not execution_entry_status or execution_entry_status == "missing":
            out["execution_entry_status"] = recovered_status or "missing"
            execution_entry_status = str(out.get("execution_entry_status") or "").strip().lower()
    if bool(out.get("entry_recovered")) and execution_entry is not None and execution_entry_source in {"", "none"}:
        out["execution_entry_source"] = "recovered_fallback"
        execution_entry_source = "recovered_fallback"
    if execution_entry_source == "last" and not should_allow_last_execution_fallback(out):
        out["execution_entry"] = None
        out["execution_entry_source"] = "none"
        if execution_entry_status == "executable":
            out["execution_entry_status"] = "non_executable"
            execution_entry_status = "non_executable"
        execution_entry = None
        execution_entry_source = "none"
    if bool(out.get("entry_recovered")) and execution_entry is not None:
        out["execution_entry_status"] = "non_executable"
        out["execution_allowed"] = False
        out["execution_status"] = "advisory_only"
        out["is_executable"] = False
        execution_entry_status = "non_executable"

    # Preserve a real executable entry if a downstream normalizer dropped the
    # duplicated display/entry fields but kept the canonical execution entry.
    executable_ready = _has_executable_entry_truth(
        execution_entry=execution_entry,
        execution_entry_source=execution_entry_source,
        execution_entry_status=execution_entry_status,
    )
    if executable_ready and display_entry is None:
        display_entry = execution_entry
        out["display_entry"] = display_entry
        if display_entry_source not in ENTRY_SOURCE_ENUM or display_entry_source == "none":
            display_entry_source = execution_entry_source if execution_entry_source in ENTRY_SOURCE_ENUM else "last"
            out["display_entry_source"] = display_entry_source
        if display_entry_status not in DISPLAY_ENTRY_STATUSES or display_entry_status == "missing":
            display_entry_status = "displayable"
            out["display_entry_status"] = display_entry_status
        out["entry_clear_reason"] = None

    if display_entry is not None and entry is None:
        entry = display_entry
        out["entry"] = entry
    if display_entry is not None:
        if (_safe_lower_text(out.get("entry_source")) or "none") == "none":
            out["entry_source"] = display_entry_source
        if entry_status not in ENTRY_STATUSES or entry_status == "missing":
            out["entry_status"] = display_entry_status
            entry_status = display_entry_status
        if entry_display_status not in ENTRY_STATUSES or entry_display_status == "missing":
            out["entry_display_status"] = display_entry_status
            entry_display_status = display_entry_status
    if display_entry is not None and execution_entry is None:
        out["display_entry_status"] = "displayable"
        if entry is not None:
            out["entry_status"] = "displayable"
            entry_status = "displayable"
        out["entry_display_status"] = "displayable"
        entry_display_status = "displayable"

    missing_entry = entry is None or entry_status == "missing"
    execution_status = str(out.get("execution_status") or "").strip().lower()
    readiness = str(out.get("readiness") or "").strip().upper()
    final_action = str(out.get("final_action") or "").strip().upper()
    permission = str(out.get("permission") or "").strip().upper()
    row_status = str(out.get("status") or "").strip().upper()
    claims_executable = execution_status == "executable" or bool(out.get("is_executable")) or readiness == "READY" or final_action == "EXECUTE" or permission == "EXECUTE" or row_status == "READY"
    missing_executable_entry = not executable_ready
    if not claims_executable:
        return _apply_post_level_entry_mutation_policy(
            out,
            entry_before=entry_before,
            display_before=display_before,
            execution_before=execution_before,
        )
    if missing_executable_entry and display_entry is not None:
        out["execution_entry"] = None
        out["execution_entry_source"] = "none"
        out["execution_entry_status"] = "non_executable"
        out["display_entry_status"] = "displayable"
        out["entry_status"] = "displayable"
        execution_entry = None
        execution_entry_source = "none"
        execution_entry_status = "non_executable"
        display_entry_status = "displayable"
        entry_status = "displayable"
    if not missing_entry and not missing_executable_entry:
        return _apply_post_level_entry_mutation_policy(
            out,
            entry_before=entry_before,
            display_before=display_before,
            execution_before=execution_before,
        )

    has_hard_blockers = bool(_normalize_blockers(out.get("hard_blockers")))
    display_only_entry = display_entry is not None and missing_executable_entry and entry_status == "displayable"
    if not display_only_entry and not has_hard_blockers:
        hard_blockers = _normalize_blockers(out.get("hard_blockers"))
        blockers = _normalize_blockers(out.get("blockers"))
        if "MISSING_ENTRY" not in hard_blockers:
            hard_blockers.append("MISSING_ENTRY")
        if "MISSING_ENTRY" not in blockers:
            blockers.append("MISSING_ENTRY")
        out["hard_blockers"] = hard_blockers
        out["blockers"] = blockers
        has_hard_blockers = True
    out["execution_status"] = "blocked" if has_hard_blockers or not display_only_entry else "advisory_only"
    out["is_executable"] = False
    if readiness == "READY":
        out["readiness"] = "BLOCKED" if has_hard_blockers or not display_only_entry else "ADVISORY_ONLY"
    if final_action == "EXECUTE":
        out["final_action"] = "BLOCK" if has_hard_blockers or not display_only_entry else "ADVISORY_ONLY"
    if permission == "EXECUTE":
        out["permission"] = "BLOCK" if has_hard_blockers or not display_only_entry else "ADVISORY_ONLY"
    if row_status == "READY":
        out["status"] = "INVALID" if has_hard_blockers or not display_only_entry else "ADVISORY_ONLY"
    if not _normalize_text(out.get("entry_clear_reason")):
        reason = "missing_execution_entry" if missing_executable_entry else str(out.get("entry_status") or "missing_entry").strip().lower()
        out["entry_clear_reason"] = reason or "missing_entry"
    if not _normalize_text(out.get("entry_block_code")) and _normalize_text(out.get("entry_clear_reason")):
        out["entry_block_code"] = _normalize_text(out.get("entry_clear_reason"))
    return _apply_post_level_entry_mutation_policy(
        out,
        entry_before=entry_before,
        display_before=display_before,
        execution_before=execution_before,
    )


def validate_advisory_row(payload: dict[str, Any], *, allow_legacy: bool = False) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AdvisorySchemaError("advisory row must be a dict")
    out = _legacy_adapter(payload) if allow_legacy and not _looks_like_canonical(payload) else dict(payload)
    derived_ts_epoch = _derive_ts_epoch(out)
    if derived_ts_epoch is None:
        if _has_timestamp_hint(out):
            raise AdvisorySchemaError("ts_epoch must be numeric or derivable from timestamp")
        derived_ts_epoch = datetime.now(timezone.utc).timestamp()
    if derived_ts_epoch is not None:
        out["ts_epoch"] = float(derived_ts_epoch)
        out["timestamp"] = _utc_timestamp_from_epoch(derived_ts_epoch)
        out["ts_utc"] = out["timestamp"]
        out["ts_ist"] = _ist_timestamp_from_epoch(derived_ts_epoch)
        out = _apply_explicit_display_timestamps(out, float(derived_ts_epoch))
    instrument_type_before = _normalize_text(out.get("instrument_type") or out.get("instrument"))
    inferred_type, inferred_source = _infer_instrument_type(out)
    if inferred_type:
        out["instrument_type"] = inferred_type
        out.setdefault("instrument_type_source", inferred_source)
        if not instrument_type_before and inferred_source == "fallback":
            out.setdefault("failure_reason", "instrument_type_backfilled")
    for field in REQUIRED_FIELDS:
        if field not in out:
            raise AdvisorySchemaError(f"missing required field: {field}")
    execution_entry_before = out.get("execution_entry")
    execution_entry_status_before = out.get("execution_entry_status")
    out = _enforce_executable_entry_invariant(out)
    out["row_kind"] = _derive_row_kind(out)
    out["non_canonical_levels"] = bool(out.get("non_canonical_levels")) or out["row_kind"] != CANONICAL_ROW_KIND
    out["levels_recomputed_from_final_entry"] = bool(out.get("levels_recomputed_from_final_entry", False))
    out["level_recompute_reason"] = _normalize_text(out.get("level_recompute_reason"))
    append_execution_entry_trace(
        module="core.advisory_schema",
        stage="validate_advisory_row",
        row=out,
        execution_entry_before=execution_entry_before,
        execution_entry_after=out.get("execution_entry"),
        execution_entry_status_before=execution_entry_status_before,
        execution_entry_status_after=out.get("execution_entry_status"),
        extra={
            "execution_entry_source": out.get("execution_entry_source"),
            "display_entry": out.get("display_entry"),
            "display_entry_status": out.get("display_entry_status"),
            "derivation_reason": out.get("_execution_entry_derivation_reason"),
            "derivation_source_chain": out.get("_execution_entry_derivation_source_chain"),
        },
    )
    level_invariant_error = validate_price_level_invariants(out)
    if level_invariant_error:
        if _candidate_row_corruption_log_enabled():
            log_corrupt_advisory_row(out, level_invariant_error)
        raise AdvisorySchemaError(level_invariant_error)

    trade_id = _normalize_text(out.get("trade_id"))
    strategy_id = _normalize_text(out.get("strategy_id"))
    advisory_id = _normalize_text(out.get("advisory_id"))
    symbol = _normalize_text(out.get("symbol"))
    strategy_name = _normalize_text(out.get("strategy_name"))
    identity = infer_candidate_identity(out)
    candidate_type = _normalize_text(out.get("candidate_type")) or identity.get("candidate_type") or "unknown"
    strategy_family = _normalize_text(out.get("strategy_family")) or identity.get("strategy_family") or "unknown"
    setup_variant = _normalize_text(out.get("setup_variant")) or identity.get("setup_variant") or "unknown"
    direction = _normalize_text(out.get("direction")) or identity.get("direction") or "UNKNOWN"
    candidate_status = _normalize_text(out.get("candidate_status")) or _derive_candidate_status(out)
    ts_epoch = _coerce_ts_epoch(out.get("ts_epoch"))
    timestamp = _normalize_text(out.get("timestamp"))
    instrument_type = _normalize_text(out.get("instrument_type"))
    execution_entry = _safe_float(out.get("execution_entry"))
    execution_entry_source = _safe_lower_text(out.get("execution_entry_source")) or "none"
    execution_entry_status = str(out.get("execution_entry_status") or "").strip().lower()
    display_entry = _safe_float(out.get("display_entry"))
    display_entry_source = _safe_lower_text(out.get("display_entry_source")) or "none"
    display_entry_status = str(out.get("display_entry_status") or "").strip().lower()
    entry_display_status = str(out.get("entry_display_status") or display_entry_status or "").strip().lower()
    entry_reason = _normalize_text(out.get("entry_reason"))
    entry_clear_reason = _normalize_text(out.get("entry_clear_reason"))
    entry_block_code = _normalize_text(out.get("entry_block_code"))
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
    quote_age_sec = _canonical_quote_age_sec(out)
    entry = _safe_float(out.get("entry"))
    execution_status = str(out.get("execution_status") or "").strip().lower()
    permission = str(out.get("permission") or "").strip().upper()
    final_action = str(out.get("final_action") or "").strip().upper()
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
        ("builder_confidence", _safe_float(out.get("builder_confidence"))),
        ("permission_confidence", _safe_float(out.get("permission_confidence"))),
        ("gating_base_confidence", _safe_float(out.get("gating_base_confidence"))),
        ("gating_final_confidence", _safe_float(out.get("gating_final_confidence"))),
        ("sizing_confluence_score", _safe_float(out.get("sizing_confluence_score"))),
        ("ml_proba_input", _safe_float(out.get("ml_proba_input"))),
        ("confluence_input", _safe_float(out.get("confluence_input"))),
        ("confidence_size_multiplier", _safe_float(out.get("confidence_size_multiplier"))),
        ("opportunity_score", _safe_float(out.get("opportunity_score"))),
        ("opportunity_size_multiplier", _safe_float(out.get("opportunity_size_multiplier"))),
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
    if display_entry is not None and display_entry_status not in {"displayable"}:
        raise AdvisorySchemaError("display_entry requires display_entry_status=displayable")
    if execution_entry is not None and execution_entry_status != "executable":
        raise AdvisorySchemaError("execution_entry requires execution_entry_status=executable")
    if entry_display_status and entry_display_status != display_entry_status:
        raise AdvisorySchemaError("entry_display_status must equal display_entry_status")
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
    if final_action == "BLOCK" and not hard_blockers and not entry_block_code:
        raise AdvisorySchemaError("final_action=BLOCK requires hard_blockers or entry_block_code")

    trade_lifecycle_state = _normalize_text(out.get("trade_lifecycle_state"))
    trade_lifecycle_reason = _normalize_text(out.get("trade_lifecycle_reason"))
    trade_lifecycle_ts = _normalize_text(out.get("trade_lifecycle_ts"))
    trade_lifecycle_history = out.get("trade_lifecycle_history") or []
    if trade_lifecycle_state and trade_lifecycle_state not in TRADE_LIFECYCLE_STATES:
        raise AdvisorySchemaError(f"invalid trade_lifecycle_state: {trade_lifecycle_state}")
    if not isinstance(trade_lifecycle_history, list):
        raise AdvisorySchemaError("trade_lifecycle_history must be a list")
    normalized_trade_lifecycle_history = []
    for event in trade_lifecycle_history:
        if not isinstance(event, dict):
            raise AdvisorySchemaError("trade_lifecycle_history events must be dicts")
        event_state = _normalize_text(event.get("state"))
        if event_state and event_state not in TRADE_LIFECYCLE_STATES:
            raise AdvisorySchemaError(f"invalid trade_lifecycle_history state: {event_state}")
        normalized_trade_lifecycle_history.append(
            {
                "state": event_state or None,
                "reason": _normalize_text(event.get("reason")),
                "timestamp": _normalize_text(event.get("timestamp")),
            }
        )

    out["trade_id"] = trade_id
    out["strategy_id"] = strategy_id
    out["advisory_id"] = advisory_id
    out["symbol"] = symbol
    out["strategy_name"] = strategy_name
    out["candidate_type"] = candidate_type
    out["strategy_family"] = strategy_family
    out["setup_variant"] = setup_variant
    out["direction"] = direction
    out["candidate_status"] = candidate_status
    out["row_kind"] = _derive_row_kind(out)
    out["non_canonical_levels"] = bool(out.get("non_canonical_levels")) or out["row_kind"] != CANONICAL_ROW_KIND
    out["levels_recomputed_from_final_entry"] = bool(out.get("levels_recomputed_from_final_entry", False))
    out["level_recompute_reason"] = _normalize_text(out.get("level_recompute_reason"))
    out["ts_epoch"] = float(ts_epoch)
    out["timestamp"] = _utc_timestamp_from_epoch(ts_epoch)
    out["ts_utc"] = out["timestamp"]
    out["ts_ist"] = _ist_timestamp_from_epoch(ts_epoch)
    out = _apply_explicit_display_timestamps(out, float(ts_epoch))
    out["instrument_type"] = instrument_type.upper()
    out["execution_entry"] = execution_entry
    out["execution_entry_source"] = execution_entry_source
    out["execution_entry_status"] = execution_entry_status
    out["display_entry"] = display_entry
    out["display_entry_source"] = display_entry_source
    out["display_entry_status"] = display_entry_status
    out["entry_display_status"] = entry_display_status or display_entry_status
    out["entry_reason"] = entry_reason
    out["entry_clear_reason"] = entry_clear_reason
    out["entry_block_code"] = entry_block_code or entry_clear_reason
    out["entry"] = entry
    out["entry_status"] = display_entry_status
    out["confidence"] = confidence
    out["builder_confidence"] = _safe_float(out.get("builder_confidence"))
    out["permission_confidence"] = _safe_float(out.get("permission_confidence"))
    out["gating_base_confidence"] = _safe_float(out.get("gating_base_confidence"))
    out["gating_final_confidence"] = _safe_float(out.get("gating_final_confidence"))
    if out["gating_final_confidence"] is not None:
        confidence_final = out["gating_final_confidence"]
        confidence = confidence_final
    out["sizing_confluence_score"] = _safe_float(out.get("sizing_confluence_score"))
    out["sizing_reason"] = _normalize_text(out.get("sizing_reason"))
    out["ml_proba_input"] = _safe_float(out.get("ml_proba_input"))
    out["confluence_input"] = _safe_float(out.get("confluence_input"))
    out["ml_proba_source"] = _normalize_text(out.get("ml_proba_source"))
    out["confluence_source"] = _normalize_text(out.get("confluence_source"))
    out["confidence_size_multiplier"] = _safe_float(out.get("confidence_size_multiplier"))
    out["final_qty"] = int(out["final_qty"]) if _safe_float(out.get("final_qty")) is not None else None
    out["rank_score"] = _safe_float(out.get("rank_score"))
    out["setup_strength"] = _safe_float(out.get("setup_strength"))
    out["regime_fit"] = _safe_float(out.get("regime_fit"))
    out["liquidity_score"] = _safe_float(out.get("liquidity_score"))
    out["spread_score"] = _safe_float(out.get("spread_score"))
    out["rr_score"] = _safe_float(out.get("rr_score"))
    out["timing_score"] = _safe_float(out.get("timing_score"))
    out["penalty_score"] = _safe_float(out.get("penalty_score"))
    out["score_breakdown"] = _normalize_mapping(out.get("score_breakdown"))
    out["penalty_reasons"] = _normalize_blockers(out.get("penalty_reasons"))
    out["score_inputs_used"] = _normalize_mapping(out.get("score_inputs_used"))
    out["opportunity_score"] = _safe_float(out.get("opportunity_score"))
    out["opportunity_rank"] = out.get("opportunity_rank")
    out["rank_global"] = out.get("rank_global")
    out["rank_within_symbol"] = out.get("rank_within_symbol")
    out["opportunity_bucket"] = _normalize_text(out.get("opportunity_bucket"))
    out["selected_for_execution"] = bool(out.get("selected_for_execution", False))
    out["selection_reason"] = _normalize_text(out.get("selection_reason"))
    out["size_multiplier_reason"] = _normalize_text(out.get("size_multiplier_reason"))
    out["opportunity_size_multiplier"] = _safe_float(out.get("opportunity_size_multiplier"))
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
    out["confidence"] = confidence_final
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
    out["price_age_sec"] = quote_age_sec
    out["option_age_sec"] = quote_age_sec
    out["decision_explain"] = decision_explain
    out["market_open"] = market_open
    out["trade_lifecycle_state"] = trade_lifecycle_state
    out["trade_lifecycle_reason"] = trade_lifecycle_reason
    out["trade_lifecycle_ts"] = trade_lifecycle_ts
    out["trade_lifecycle_history"] = normalized_trade_lifecycle_history
    return out


def serialize_advisory_row(payload: dict[str, Any], *, allow_legacy: bool = False) -> dict[str, Any]:
    prepared = _enforce_executable_entry_invariant(dict(payload)) if isinstance(payload, dict) else payload
    return validate_advisory_row(prepared, allow_legacy=allow_legacy)


def deserialize_advisory_row(payload: dict[str, Any], *, allow_legacy: bool = False) -> dict[str, Any]:
    return validate_advisory_row(payload, allow_legacy=allow_legacy)
