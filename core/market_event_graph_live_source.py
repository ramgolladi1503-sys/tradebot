"""Read-only live captured-metadata source contract for Market Event Graph.

This module does not fetch market data, subscribe to feeds, call brokers, place
orders, or compute outcomes. It only validates and appends completed interval
metadata that an existing runtime boundary supplies.
"""

from __future__ import annotations

import json
import math
import statistics
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from core.fs_utils import ensure_parent_dir
from core.market_event_graph_breadth_producer import frozen_threshold_metadata, initial_market_event_graph_runtime_state
from core.market_event_graph_contract import FROZEN_THRESHOLDS, metadata_has_frozen_contract, thresholds_match_frozen

LIVE_SOURCE_SCHEMA_VERSION = 1
SOURCE_KIND_LIVE_CAPTURED_METADATA = "LIVE_CAPTURED_METADATA"
SOURCE_KIND_REPLAY = "REPLAY_FIXTURE"

REASON_OK = "OK"
REASON_ROW_NOT_MAPPING = "ROW_NOT_MAPPING"
REASON_NOT_LIVE_CAPTURED = "NOT_LIVE_CAPTURED_METADATA"
REASON_REPLAY_FIXTURE_FORBIDDEN = "REPLAY_FIXTURE_FORBIDDEN_IN_LIVE_SOURCE"
REASON_MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
REASON_MISSING_AUTHORITY_FLAG = "MISSING_AUTHORITY_FLAG"
REASON_AUTHORITY_FLAG_UNSAFE = "AUTHORITY_FLAG_UNSAFE"
REASON_FROZEN_PROVENANCE_MISMATCH = "FROZEN_PROVENANCE_MISMATCH"
REASON_RUNTIME_STATE_INVALID = "RUNTIME_STATE_INVALID"
REASON_INDEX_BAR_MISSING = "INDEX_BAR_MISSING"
REASON_COMPLETED_BARS_MISSING = "COMPLETED_CONSTITUENT_BARS_MISSING"
REASON_PARTIAL_INTERVAL = "PARTIAL_INTERVAL"
REASON_TIMESTAMP_INVALID = "TIMESTAMP_INVALID"
REASON_FUTURE_SOURCE_TIMESTAMP = "FUTURE_SOURCE_TIMESTAMP"
REASON_CONSTITUENT_RETURNS_MISSING = "CONSTITUENT_RETURNS_MISSING"
REASON_CONSTITUENT_RETURNS_NONFINITE = "CONSTITUENT_RETURNS_NONFINITE"
REASON_INCOMPLETE_UNIVERSE = "INCOMPLETE_UNIVERSE"
REASON_DUPLICATE_INTERVAL = "DUPLICATE_INTERVAL"

REQUIRED_ROW_FIELDS = (
    "schema_version",
    "source_kind",
    "run_id",
    "session_date",
    "symbol",
    "interval_end",
    "ts_epoch",
    "source_bar_end_epoch",
    "index_bar_available",
    "expected_constituents",
    "completed_constituent_bars",
    "missing_constituents",
    "stale_constituents",
    "duplicate_constituents",
    "misaligned_constituents",
    "late_constituents",
    "runtime_source_identifier",
    "market_event_graph_runtime_state",
)

AUTHORITY_FLAGS = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "allowed_for_live_execution": False,
    "append": True,
}


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reason: str
    details: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"accepted": self.accepted, "reason": self.reason, "details": list(self.details)}


@dataclass(frozen=True)
class ExportResult:
    written: bool
    reason: str
    path: str
    row: dict[str, Any] | None = None
    details: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "written": self.written,
            "reason": self.reason,
            "path": self.path,
            "row": dict(self.row or {}),
            "details": list(self.details),
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }


def default_live_capture_path(base_dir: Path | str = "runtime/market_event_graph_live_shadow") -> Path:
    return Path(base_dir) / "captured_metadata.jsonl"


def new_run_id(prefix: str = "meg-live") -> str:
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:12]}"


def build_live_captured_metadata_row(
    *,
    session_date: str,
    symbol: str,
    interval_end: str,
    ts_epoch: float,
    source_bar_end_epoch: float,
    index_bar: Mapping[str, Any] | None,
    constituent_bars: Sequence[Mapping[str, Any]],
    expected_constituents: int,
    run_id: str,
    runtime_source_identifier: str,
    missing_constituents: Sequence[str] | None = None,
    stale_constituents: Sequence[str] | None = None,
    duplicate_constituents: Sequence[str] | None = None,
    misaligned_constituents: Sequence[str] | None = None,
    late_constituents: Sequence[str] | None = None,
    duplicate_interval: bool = False,
) -> dict[str, Any]:
    """Build one canonical row from already-completed live metadata."""

    normalized_bars = [_normalize_constituent_bar(row, session_date=session_date) for row in constituent_bars]
    index_ret1 = _index_ret1(index_bar)
    latest_bar = {
        "ts_epoch": float(ts_epoch),
        "source_bar_end_epoch": float(source_bar_end_epoch),
        "session_date": str(session_date),
        "index_ret1": index_ret1,
        "constituent_ret1": [_return_from_bar(row) for row in normalized_bars],
        "constituent_symbols": [str(row.get("symbol") or row.get("instrument") or "") for row in normalized_bars],
        "completed": True,
    }
    row = {
        "schema_version": LIVE_SOURCE_SCHEMA_VERSION,
        "source_kind": SOURCE_KIND_LIVE_CAPTURED_METADATA,
        "run_id": str(run_id),
        "session_date": str(session_date),
        "symbol": str(symbol or "").upper(),
        "interval_end": str(interval_end),
        "ts_epoch": float(ts_epoch),
        "source_bar_end_epoch": float(source_bar_end_epoch),
        "index_source_bar_end_epoch": float(source_bar_end_epoch),
        "index_bar_available": index_bar is not None,
        "index_bar": dict(index_bar or {}),
        "index_ret1": index_ret1,
        "expected_constituents": int(expected_constituents),
        "completed_constituent_bars": [latest_bar],
        "constituent_bar_details": normalized_bars,
        "missing_constituents": _string_list(missing_constituents),
        "stale_constituents": _string_list(stale_constituents),
        "duplicate_constituents": _string_list(duplicate_constituents),
        "misaligned_constituents": _string_list(misaligned_constituents),
        "late_constituents": _string_list(late_constituents),
        "duplicate_interval": bool(duplicate_interval),
        "runtime_source_identifier": str(runtime_source_identifier),
        "source_generated_at_epoch": float(time.time()),
        "market_event_graph_runtime_state": initial_market_event_graph_runtime_state(str(session_date)),
        **frozen_threshold_metadata(),
        **AUTHORITY_FLAGS,
    }
    return row


class LiveCapturedMetadataExporter:
    """Crash-tolerant append-only writer for already-built completed intervals."""

    def __init__(self, path: Path | str, *, run_id: str | None = None) -> None:
        self.path = Path(path)
        self.run_id = run_id or new_run_id()

    def export_row(self, row: Mapping[str, Any]) -> ExportResult:
        payload = dict(row)
        payload.setdefault("run_id", self.run_id)
        payload.setdefault("source_kind", SOURCE_KIND_LIVE_CAPTURED_METADATA)
        payload.setdefault("schema_version", LIVE_SOURCE_SCHEMA_VERSION)
        for key, value in AUTHORITY_FLAGS.items():
            payload.setdefault(key, value)
        try:
            if _is_duplicate_interval(self.path, payload):
                payload["duplicate_interval"] = True
            validation = validate_live_captured_metadata_row(payload)
            if not validation.accepted:
                return ExportResult(False, validation.reason, str(self.path), row=payload, details=validation.details)
            target = ensure_parent_dir(self.path)
            with target.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
                fh.flush()
            return ExportResult(True, REASON_OK, str(self.path), row=payload)
        except Exception as exc:
            return ExportResult(False, "WRITE_FAILED", str(self.path), row=payload, details=(f"{type(exc).__name__}:{exc}",))


def validate_live_captured_metadata_row(row: Mapping[str, Any]) -> ValidationResult:
    if not isinstance(row, Mapping):
        return ValidationResult(False, REASON_ROW_NOT_MAPPING)
    missing = [key for key in REQUIRED_ROW_FIELDS if key not in row]
    if missing:
        return ValidationResult(False, REASON_MISSING_REQUIRED_FIELD, tuple(missing))
    if str(row.get("source_kind") or "") == SOURCE_KIND_REPLAY:
        return ValidationResult(False, REASON_REPLAY_FIXTURE_FORBIDDEN)
    if str(row.get("source_kind") or "") != SOURCE_KIND_LIVE_CAPTURED_METADATA:
        return ValidationResult(False, REASON_NOT_LIVE_CAPTURED)
    for key, expected in AUTHORITY_FLAGS.items():
        if key not in row:
            return ValidationResult(False, REASON_MISSING_AUTHORITY_FLAG, (key,))
        if bool(row.get(key)) is not bool(expected):
            return ValidationResult(False, REASON_AUTHORITY_FLAG_UNSAFE, (key,))
    if not metadata_has_frozen_contract(row) or not thresholds_match_frozen(row.get("market_event_graph_thresholds") or {}):
        return ValidationResult(False, REASON_FROZEN_PROVENANCE_MISMATCH)
    runtime_state = row.get("market_event_graph_runtime_state")
    if not isinstance(runtime_state, Mapping) or str(runtime_state.get("session_date") or "") != str(row.get("session_date")):
        return ValidationResult(False, REASON_RUNTIME_STATE_INVALID)
    if row.get("index_bar_available") is not True or row.get("index_ret1") is None:
        return ValidationResult(False, REASON_INDEX_BAR_MISSING)
    bars = row.get("completed_constituent_bars")
    if not isinstance(bars, Sequence) or isinstance(bars, (str, bytes)) or not bars:
        return ValidationResult(False, REASON_COMPLETED_BARS_MISSING)
    latest = bars[-1]
    if not isinstance(latest, Mapping):
        return ValidationResult(False, REASON_COMPLETED_BARS_MISSING)
    if latest.get("completed") is not True or latest.get("is_completed") is False:
        return ValidationResult(False, REASON_PARTIAL_INTERVAL)
    details = row.get("constituent_bar_details")
    if isinstance(details, Sequence) and not isinstance(details, (str, bytes)):
        for item in details:
            if isinstance(item, Mapping) and (item.get("completed") is False or item.get("is_completed") is False):
                return ValidationResult(False, REASON_PARTIAL_INTERVAL)
    timestamps = (row.get("ts_epoch"), row.get("source_bar_end_epoch"), latest.get("ts_epoch"), latest.get("source_bar_end_epoch"))
    try:
        ts_epoch, source_end, latest_ts, latest_source_end = (float(value) for value in timestamps)
    except Exception:
        return ValidationResult(False, REASON_TIMESTAMP_INVALID)
    if not all(math.isfinite(value) and value > 0.0 for value in (ts_epoch, source_end, latest_ts, latest_source_end)):
        return ValidationResult(False, REASON_TIMESTAMP_INVALID)
    if source_end > ts_epoch or latest_source_end > latest_ts:
        return ValidationResult(False, REASON_FUTURE_SOURCE_TIMESTAMP)
    if source_end != latest_source_end or ts_epoch != latest_ts:
        return ValidationResult(False, REASON_TIMESTAMP_INVALID)
    returns = latest.get("constituent_ret1")
    if not isinstance(returns, Sequence) or isinstance(returns, (str, bytes)):
        return ValidationResult(False, REASON_CONSTITUENT_RETURNS_MISSING)
    finite = [_finite_float(value) for value in returns]
    if any(value is None for value in finite):
        return ValidationResult(False, REASON_CONSTITUENT_RETURNS_NONFINITE)
    try:
        expected = int(row.get("expected_constituents"))
    except Exception:
        return ValidationResult(False, REASON_INCOMPLETE_UNIVERSE)
    if len(returns) != expected:
        return ValidationResult(False, REASON_INCOMPLETE_UNIVERSE, (f"expected={expected}", f"observed={len(returns)}"))
    if bool(row.get("duplicate_interval")):
        return ValidationResult(False, REASON_DUPLICATE_INTERVAL)
    return ValidationResult(True, REASON_OK)


def load_validated_live_jsonl(path: Path | str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            text = line.strip()
            if not text:
                continue
            row = json.loads(text)
            validation = validate_live_captured_metadata_row(row)
            if not validation.accepted:
                raise ValueError(f"{path}:{lineno}:{validation.reason}:{','.join(validation.details)}")
            rows.append(dict(row))
    return rows


def independent_raw_jsonl_audit(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {
            "source_path": str(source),
            "total_raw_intervals": 0,
            "accepted_intervals": 0,
            "rejected_intervals": 0,
            "rejected_by_reason": {"INPUT_MISSING": 1},
            "valid_coverage_ratio": 0.0,
            "constituent_count": _count_summary([]),
            "identity_issue_counts": {
                "missing_constituents": 0,
                "stale_constituents": 0,
                "duplicate_constituents": 0,
                "misaligned_constituents": 0,
                "late_constituents": 0,
            },
            "non_monotonic_timestamps": 0,
            "future_source_timestamp_violations": 0,
            "completed_graph_count": 0,
            "candidate_trace_count": 0,
            "fallback_quote_count": 0,
            "authority_flags": dict(AUTHORITY_FLAGS),
            "verdict": "FAIL_RAW_LIVE_JSONL_AUDIT",
        }
    total = 0
    accepted = 0
    rejected = Counter()
    constituent_counts: list[int] = []
    identity_counts = Counter()
    non_monotonic_ts = 0
    future_source_timestamp_violations = 0
    prior_ts: float | None = None
    for row in _iter_jsonl(path):
        total += 1
        validation = validate_live_captured_metadata_row(row) if isinstance(row, Mapping) else ValidationResult(False, REASON_ROW_NOT_MAPPING)
        if validation.accepted:
            accepted += 1
        else:
            rejected[validation.reason] += 1
        latest = _latest_bar(row)
        count = _constituent_count(latest)
        if count is not None:
            constituent_counts.append(count)
        for key in ("missing_constituents", "stale_constituents", "duplicate_constituents", "misaligned_constituents", "late_constituents"):
            identity_counts[key] += len(_string_list(row.get(key) if isinstance(row, Mapping) else None))
        ts = _safe_float(row.get("ts_epoch") if isinstance(row, Mapping) else None)
        source_end = _safe_float(row.get("source_bar_end_epoch") if isinstance(row, Mapping) else None)
        if ts is not None:
            if prior_ts is not None and ts <= prior_ts:
                non_monotonic_ts += 1
            prior_ts = ts
        if ts is not None and source_end is not None and source_end > ts:
            future_source_timestamp_violations += 1
    return {
        "source_path": str(path),
        "total_raw_intervals": total,
        "accepted_intervals": accepted,
        "rejected_intervals": total - accepted,
        "rejected_by_reason": dict(sorted(rejected.items())),
        "valid_coverage_ratio": (accepted / total) if total else 0.0,
        "constituent_count": _count_summary(constituent_counts),
        "identity_issue_counts": dict(identity_counts),
        "non_monotonic_timestamps": non_monotonic_ts,
        "future_source_timestamp_violations": future_source_timestamp_violations,
        "completed_graph_count": 0,
        "candidate_trace_count": 0,
        "fallback_quote_count": 0,
        "authority_flags": dict(AUTHORITY_FLAGS),
        "verdict": "PASS_RAW_LIVE_JSONL_AUDIT" if total and accepted == total else "FAIL_RAW_LIVE_JSONL_AUDIT",
    }


def _iter_jsonl(path: Path | str) -> Iterable[Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if not text:
                continue
            try:
                yield json.loads(text)
            except Exception:
                yield {"source_kind": "PARSE_ERROR"}


def _normalize_constituent_bar(row: Mapping[str, Any], *, session_date: str) -> dict[str, Any]:
    out = dict(row)
    out.setdefault("session_date", session_date)
    out["completed"] = bool(out.get("completed", True))
    return out


def _return_from_bar(row: Mapping[str, Any]) -> float:
    for key in ("ret1", "constituent_ret1", "return", "return_1m"):
        if key in row:
            value = _finite_float(row.get(key))
            if value is not None:
                return value
    open_px = _finite_float(row.get("open"))
    close_px = _finite_float(row.get("close"))
    if open_px is not None and open_px != 0.0 and close_px is not None:
        return (close_px - open_px) / open_px
    return float("nan")


def _index_ret1(index_bar: Mapping[str, Any] | None) -> float | None:
    if not isinstance(index_bar, Mapping):
        return None
    for key in ("ret1", "index_ret1", "return", "return_1m"):
        value = _finite_float(index_bar.get(key))
        if value is not None:
            return value
    open_px = _finite_float(index_bar.get("open"))
    close_px = _finite_float(index_bar.get("close"))
    if open_px is not None and open_px != 0.0 and close_px is not None:
        return (close_px - open_px) / open_px
    return None


def _is_duplicate_interval(path: Path, row: Mapping[str, Any]) -> bool:
    if not path.exists():
        return False
    key = (str(row.get("session_date") or ""), _safe_float(row.get("source_bar_end_epoch")))
    for existing in _iter_jsonl(path):
        if not isinstance(existing, Mapping):
            continue
        existing_key = (str(existing.get("session_date") or ""), _safe_float(existing.get("source_bar_end_epoch")))
        if existing_key == key:
            return True
    return False


def _latest_bar(row: Any) -> Mapping[str, Any]:
    if not isinstance(row, Mapping):
        return {}
    bars = row.get("completed_constituent_bars")
    if isinstance(bars, Sequence) and not isinstance(bars, (str, bytes)) and bars and isinstance(bars[-1], Mapping):
        return bars[-1]
    return {}


def _constituent_count(bar: Mapping[str, Any]) -> int | None:
    values = bar.get("constituent_ret1") if isinstance(bar, Mapping) else None
    if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
        return len(values)
    return None


def _count_summary(values: Sequence[int]) -> dict[str, Any]:
    if not values:
        return {"min": None, "max": None, "median": None}
    return {"min": min(values), "max": max(values), "median": statistics.median(values)}


def _finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if not math.isfinite(out):
        return None
    return out


def _safe_float(value: Any) -> float | None:
    return _finite_float(value)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value if str(item or "").strip()]


__all__ = [
    "AUTHORITY_FLAGS",
    "ExportResult",
    "LiveCapturedMetadataExporter",
    "ValidationResult",
    "build_live_captured_metadata_row",
    "default_live_capture_path",
    "independent_raw_jsonl_audit",
    "load_validated_live_jsonl",
    "new_run_id",
    "validate_live_captured_metadata_row",
]
