from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

TRACE_CANDIDATE_ID = "MAIN_TRADEBOT:.runtime/logs/execution_entry_trace.jsonl"
DEFAULT_MAX_LINE_BYTES = 2 * 1024 * 1024

_REQUIRED_TOP_LEVEL_KEYS = ("timestamp", "module", "stage")
_EXPECTED_TOP_LEVEL_KEYS = {
    "ts_epoch",
    "timestamp",
    "module",
    "stage",
    "trade_id",
    "symbol",
    "strategy",
    "entry",
    "display_entry",
    "expected_entry",
    "current_ltp",
    "option_ltp_source",
    "quote_source",
    "quote_validation_status",
    "permission",
    "final_action",
    "execution_entry_before",
    "execution_entry_after",
    "execution_entry_status_before",
    "execution_entry_status_after",
    "execution_allowed",
    "tradable",
    "extra",
}
_DENIED_KEY_TOKENS = (
    "outcome",
    "realized_pnl",
    "pnl",
    "profit",
    "loss",
    "future_return",
    "forward_return",
    "trade_result",
    "holdout",
    "post_trade",
)


class LocalTraceAuditError(RuntimeError):
    """Base error for local execution-trace inspection."""


class TraceMissingError(LocalTraceAuditError):
    """The declared trace does not exist as a regular file."""


class TraceHashMismatchError(LocalTraceAuditError):
    """The trace bytes do not match a caller-frozen digest."""


class TraceFormatError(LocalTraceAuditError):
    """The trace is not valid bounded UTF-8 JSONL."""


class OutcomeBearingFieldError(LocalTraceAuditError):
    """A field forbidden by the pre-outcome audit boundary was present."""


def _canonical_json(payload: Any) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def _normalized_key(value: str) -> str:
    return value.casefold().replace("-", "_").replace(" ", "_")


def _denied_key(value: str) -> bool:
    normalized = _normalized_key(value)
    return any(token in normalized for token in _DENIED_KEY_TOKENS)


def _walk_keys(value: Any, *, prefix: str = "", depth: int = 0) -> Iterable[str]:
    if depth > 12:
        raise TraceFormatError("trace_nested_structure_too_deep")
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key)
            path = f"{prefix}.{key}" if prefix else key
            if _denied_key(key):
                raise OutcomeBearingFieldError(f"outcome_or_pnl_field_present:{path}")
            yield path
            yield from _walk_keys(nested, prefix=path, depth=depth + 1)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_keys(nested, prefix=prefix, depth=depth + 1)


def _parse_timestamp(value: Any, *, line_no: int) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TraceFormatError(f"missing_or_invalid_timestamp:line={line_no}")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise TraceFormatError(f"invalid_timestamp:line={line_no}") from exc
    if parsed.tzinfo is None:
        raise TraceFormatError(f"naive_timestamp:line={line_no}")
    return parsed.astimezone(timezone.utc)


def _validated_counter_value(value: Any, *, field: str, line_no: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TraceFormatError(f"missing_or_invalid_{field}:line={line_no}")
    return value.strip()


def audit_execution_entry_trace(
    path: Path,
    *,
    expected_sha256: str | None = None,
    max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise TraceMissingError(f"trace_missing_or_not_regular:{path}")
    if max_line_bytes <= 0:
        raise ValueError("max_line_bytes must be positive")

    raw_digest = hashlib.sha256()
    semantic_digest = hashlib.sha256()
    key_manifest_digest = hashlib.sha256()
    module_counts: Counter[str] = Counter()
    stage_counts: Counter[str] = Counter()
    unknown_top_level_counts: Counter[str] = Counter()
    nested_key_counts: Counter[str] = Counter()
    record_count = 0
    blank_line_count = 0
    trade_id_present_count = 0
    strategy_present_count = 0
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None

    with path.open("rb") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            raw_digest.update(raw_line)
            if len(raw_line) > max_line_bytes:
                raise TraceFormatError(
                    f"trace_line_too_large:line={line_no}:bytes={len(raw_line)}"
                )
            stripped = raw_line.strip()
            if not stripped:
                blank_line_count += 1
                continue
            try:
                text = stripped.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise TraceFormatError(f"invalid_utf8:line={line_no}") from exc
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise TraceFormatError(f"invalid_jsonl:line={line_no}") from exc
            if not isinstance(payload, dict):
                raise TraceFormatError(f"trace_record_not_object:line={line_no}")

            for required in _REQUIRED_TOP_LEVEL_KEYS:
                if required not in payload:
                    raise TraceFormatError(
                        f"trace_required_key_missing:key={required}:line={line_no}"
                    )
            module = _validated_counter_value(
                payload.get("module"), field="module", line_no=line_no
            )
            stage = _validated_counter_value(
                payload.get("stage"), field="stage", line_no=line_no
            )
            timestamp = _parse_timestamp(payload.get("timestamp"), line_no=line_no)
            if first_timestamp is None or timestamp < first_timestamp:
                first_timestamp = timestamp
            if last_timestamp is None or timestamp > last_timestamp:
                last_timestamp = timestamp

            key_paths = sorted(set(_walk_keys(payload)))
            for key_path in key_paths:
                nested_key_counts[key_path] += 1
                key_manifest_digest.update(f"{key_path}\n".encode("utf-8"))
            for key in payload:
                if key not in _EXPECTED_TOP_LEVEL_KEYS:
                    unknown_top_level_counts[str(key)] += 1

            ts_epoch = payload.get("ts_epoch")
            if ts_epoch is not None and (
                not isinstance(ts_epoch, (int, float))
                or isinstance(ts_epoch, bool)
                or not math.isfinite(float(ts_epoch))
            ):
                raise TraceFormatError(f"invalid_ts_epoch:line={line_no}")

            module_counts[module] += 1
            stage_counts[stage] += 1
            if payload.get("trade_id") not in (None, ""):
                trade_id_present_count += 1
            if payload.get("strategy") not in (None, ""):
                strategy_present_count += 1
            semantic_digest.update(_canonical_json(payload))
            record_count += 1

    raw_sha256 = raw_digest.hexdigest()
    if expected_sha256 is not None and raw_sha256 != expected_sha256.lower():
        raise TraceHashMismatchError(
            f"trace_hash_mismatch:expected={expected_sha256.lower()}:actual={raw_sha256}"
        )

    schema_status = (
        "TRACE_SCHEMA_MATCHES_CURRENT_WRITER"
        if not unknown_top_level_counts
        else "TRACE_SCHEMA_EXTENDED_REQUIRES_HUMAN_REVIEW"
    )
    reason_codes = [
        "execution_trace_is_observational_not_signal_authority",
        "trace_does_not_prove_dataset_or_parameter_authority",
    ]
    if unknown_top_level_counts:
        reason_codes.append("unknown_top_level_fields_present")

    return {
        "schema_version": "local_unresolved_source_audit_v1",
        "candidate_id": TRACE_CANDIDATE_ID,
        "trace_sha256": raw_sha256,
        "trace_size_bytes": path.stat().st_size,
        "record_count": record_count,
        "blank_line_count": blank_line_count,
        "first_timestamp_utc": (
            first_timestamp.isoformat() if first_timestamp is not None else None
        ),
        "last_timestamp_utc": (
            last_timestamp.isoformat() if last_timestamp is not None else None
        ),
        "module_counts": dict(sorted(module_counts.items())),
        "stage_counts": dict(sorted(stage_counts.items())),
        "trade_id_present_count": trade_id_present_count,
        "strategy_present_count": strategy_present_count,
        "unknown_top_level_key_counts": dict(sorted(unknown_top_level_counts.items())),
        "observed_key_path_count": len(nested_key_counts),
        "key_path_manifest_sha256": key_manifest_digest.hexdigest(),
        "semantic_record_stream_sha256": semantic_digest.hexdigest(),
        "schema_status": schema_status,
        "source_disposition": "EXECUTION_TRACE_OBSERVATIONAL_ONLY",
        "canonical_signal_source_count": 0,
        "canonical_dataset_source_count": 0,
        "authority_reason_codes": sorted(reason_codes),
        "outcome_or_pnl_fields_present": False,
        "record_values_published": False,
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
