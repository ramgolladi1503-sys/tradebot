from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype

ALLOWED_SOURCE_ROOT = Path("runtime/upstox_candidate_replay")
REQUIRED_COLUMNS = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
CERTIFIED = "ORB_PHASE1_V2_SOURCE_MANIFEST_CERTIFIED"
NOT_CERTIFIED = "ORB_PHASE1_V2_SOURCE_MANIFEST_NOT_CERTIFIED"
SOURCE_MANIFEST_VERSION = "v2"
ALLOWED_ROOT_IDENTITY = "runtime/upstox_candidate_replay"
TIMEZONE_INTERPRETATION = "Asia/Kolkata local session representation"
SELECTION_REASON = "inventory_verified_repo_relative"


@dataclass(frozen=True)
class SourceObservation:
    manifest_index: int
    manifest_record_id: str
    manifest_symbol: str
    manifest_session_date: str
    logical_path: str
    physical_path: str
    actual_sha256: str
    byte_size: int
    observed_record: dict[str, Any]


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _semantic_payload(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [{key: value for key, value in record.items() if key != "diagnostic_absolute_path"} for record in manifest.get("records") or []]


def _normalize_symbol(value: Any) -> str:
    text = str(value or "").upper().strip()
    if "NIFTY BANK" in text or "BANKNIFTY" in text or "NIFTY BANK" in text.replace("_", " "):
        return "BANKNIFTY"
    if "NIFTY 50" in text or text == "NIFTY" or text.endswith("|NIFTY"):
        return "NIFTY"
    if "SENSEX" in text:
        return "SENSEX"
    return text


def _has_symlink_component(path: Path, *, stop_at: Path) -> bool:
    current = stop_at
    try:
        relative = path.relative_to(stop_at)
    except ValueError:
        return True
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _contained_path(source_project_root: Path | None, logical_path: str) -> tuple[Path | None, Path | None, str | None]:
    if source_project_root is None:
        return None, None, "SOURCE_AUTHORITY_NOT_SUPPLIED"
    authority = source_project_root.expanduser().resolve()
    allowed = authority / ALLOWED_SOURCE_ROOT
    if not allowed.exists():
        return None, allowed, "SOURCE_AUTHORITY_ROOT_MISSING"
    if not allowed.is_dir():
        return None, allowed, "SOURCE_AUTHORITY_ROOT_NOT_DIRECTORY"
    if _has_symlink_component(allowed, stop_at=authority):
        return None, allowed, "SOURCE_SYMLINK_COMPONENT"
    if not logical_path or Path(logical_path).is_absolute():
        return None, allowed, "SOURCE_ABSOLUTE_PATH"
    logical = Path(logical_path)
    if any(part == ".." for part in logical.parts):
        return None, allowed, "SOURCE_PATH_TRAVERSAL"
    if not logical.parts[: len(ALLOWED_SOURCE_ROOT.parts)] == ALLOWED_SOURCE_ROOT.parts:
        return None, allowed, "SOURCE_LOGICAL_PREFIX_INVALID"
    candidate = (authority / logical).resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError:
        return None, allowed, "SOURCE_ROOT_CONTAINMENT_FAILURE"
    if _has_symlink_component(candidate, stop_at=allowed):
        return None, allowed, "SOURCE_SYMLINK_COMPONENT"
    return candidate, allowed, None


def _timestamp_local_naive(series: pd.Series) -> pd.Series | None:
    timestamps = pd.to_datetime(series, errors="coerce")
    if timestamps.isna().any():
        return None
    if is_datetime64_any_dtype(timestamps.dtype) and getattr(timestamps.dt, "tz", None) is not None:
        return timestamps.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    return timestamps


def _finite_positive_ohlc(frame: pd.DataFrame) -> tuple[bool, bool]:
    finite = True
    positive = True
    for column in ("open", "high", "low", "close"):
        if not is_numeric_dtype(frame[column]):
            finite = False
            positive = False
            continue
        values = [float(value) for value in frame[column]]
        if not all(isfinite(value) for value in values):
            finite = False
        if not all(value > 0 for value in values if isfinite(value)):
            positive = False
    return finite, positive


def _format_ist_timestamp(value: pd.Timestamp) -> str:
    return f"{value.strftime('%Y-%m-%dT%H:%M:%S')}+05:30"


def _source_record_id(*, actual_sha256: str, logical_path: str, session_date: str, symbol: str) -> str:
    return _sha256_bytes(
        _canonical_json_bytes(
            {
                "actual_sha256": actual_sha256,
                "logical_path": logical_path,
                "session_date": session_date,
                "symbol": symbol,
            }
        )
    )


def _observed_source_record(
    *,
    record_index: int,
    logical_path: str,
    actual_sha256: str,
    byte_size: int,
    row_count: int,
    columns: list[str],
    normalized_symbols: list[str],
    timestamp_min: str,
    timestamp_max: str,
    session_date: str,
    symbol: str,
) -> dict[str, Any]:
    return {
        "source_manifest_version": SOURCE_MANIFEST_VERSION,
        "source_record_id": _source_record_id(
            actual_sha256=actual_sha256,
            logical_path=logical_path,
            session_date=session_date,
            symbol=symbol,
        ),
        "record_index": record_index,
        "session_date": session_date,
        "symbol": symbol,
        "logical_path": logical_path,
        "allowed_root_identity": ALLOWED_ROOT_IDENTITY,
        "actual_sha256": actual_sha256,
        "byte_size": byte_size,
        "row_count": row_count,
        "columns": columns,
        "normalized_source_symbols": normalized_symbols,
        "timestamp_min": timestamp_min,
        "timestamp_max": timestamp_max,
        "session_timezone_interpretation": TIMEZONE_INTERPRETATION,
        "selection_reason": SELECTION_REASON,
        "inventory_record_identity": {
            "logical_path": logical_path,
            "actual_sha256": actual_sha256,
            "byte_size": byte_size,
            "row_count": row_count,
        },
    }


def _compare_metadata(record: dict[str, Any], observed: dict[str, Any]) -> list[str]:
    comparisons = [
        ("source_manifest_version", "SOURCE_RECORD_VERSION_MISMATCH"),
        ("record_index", "SOURCE_RECORD_INDEX_MISMATCH"),
        ("source_record_id", "SOURCE_RECORD_ID_MISMATCH"),
        ("session_date", "SOURCE_SESSION_DATE_METADATA_MISMATCH"),
        ("symbol", "SOURCE_SYMBOL_METADATA_MISMATCH"),
        ("logical_path", "SOURCE_LOGICAL_PATH_METADATA_MISMATCH"),
        ("allowed_root_identity", "SOURCE_ALLOWED_ROOT_IDENTITY_MISMATCH"),
        ("actual_sha256", "SOURCE_ACTUAL_SHA_MISMATCH"),
        ("byte_size", "SOURCE_BYTE_SIZE_MISMATCH"),
        ("row_count", "SOURCE_ROW_COUNT_METADATA_MISMATCH"),
        ("columns", "SOURCE_COLUMN_METADATA_MISMATCH"),
        ("normalized_source_symbols", "SOURCE_NORMALIZED_SYMBOL_METADATA_MISMATCH"),
        ("timestamp_min", "SOURCE_TIMESTAMP_MIN_METADATA_MISMATCH"),
        ("timestamp_max", "SOURCE_TIMESTAMP_MAX_METADATA_MISMATCH"),
        ("session_timezone_interpretation", "SOURCE_TIMEZONE_INTERPRETATION_MISMATCH"),
        ("selection_reason", "SOURCE_SELECTION_REASON_MISMATCH"),
        ("inventory_record_identity", "SOURCE_INVENTORY_RECORD_IDENTITY_MISMATCH"),
    ]
    return [failure for field, failure in comparisons if record.get(field) != observed.get(field)]


def audit_source_manifest_file_backed(
    manifest: dict[str, Any], *, source_project_root: Path | None
) -> dict[str, Any]:
    failures: list[str] = []
    records = list(manifest.get("records") or [])
    logical_paths: list[str] = []
    observations: list[SourceObservation] = []
    resolved_count = 0
    byte_probe_count = 0
    parquet_read_count = 0
    sha_match_count = 0
    byte_size_match_count = 0
    row_count_match_count = 0
    schema_match_count = 0
    symbol_match_count = 0
    session_match_count = 0
    record_id_match_count = 0
    session_failures = 0
    containment_failures = 0
    symlink_failures = 0
    symbol_failures = 0
    ohlc_failures = 0
    schema_failures = 0
    authority_failure: str | None = None

    if manifest.get("source_manifest_version") != "v2":
        failures.append("SOURCE_MANIFEST_VERSION_MISMATCH")
    if manifest.get("record_count") != len(records):
        failures.append("SOURCE_MANIFEST_RECORD_COUNT_MISMATCH")

    expected_order = sorted(records, key=lambda item: (str(item.get("symbol")), str(item.get("session_date")), str(item.get("logical_path")), str(item.get("actual_sha256"))))
    if records != expected_order:
        failures.append("SOURCE_MANIFEST_ORDERING_MISMATCH")

    for index, record in enumerate(records):
        logical_path = str(record.get("logical_path") or "")
        logical_paths.append(logical_path)
        resolved, allowed_root, containment_failure = _contained_path(source_project_root, logical_path)
        if containment_failure:
            failures.append(containment_failure)
            if containment_failure.startswith("SOURCE_AUTHORITY"):
                authority_failure = containment_failure
            if containment_failure in {
                "SOURCE_LOGICAL_PREFIX_INVALID",
                "SOURCE_ABSOLUTE_PATH",
                "SOURCE_PATH_TRAVERSAL",
                "SOURCE_ROOT_CONTAINMENT_FAILURE",
            }:
                containment_failures += 1
            if containment_failure == "SOURCE_SYMLINK_COMPONENT":
                symlink_failures += 1
            if containment_failure.startswith("SOURCE_AUTHORITY"):
                break
            continue
        if resolved is None or allowed_root is None:
            failures.append("SOURCE_ROOT_CONTAINMENT_FAILURE")
            containment_failures += 1
            continue
        resolved_count += 1
        if not resolved.exists():
            failures.append("SOURCE_FILE_MISSING")
            continue
        if not resolved.is_file():
            failures.append("SOURCE_NOT_REGULAR_FILE")
            continue
        if resolved.is_symlink():
            failures.append("SOURCE_SYMLINK_COMPONENT")
            symlink_failures += 1
            continue
        actual_sha = _sha256_file(resolved)
        byte_size = resolved.stat().st_size
        byte_probe_count += 1
        try:
            frame = pd.read_parquet(resolved)
        except Exception:
            failures.append("SOURCE_PARQUET_READ_FAILURE")
            continue
        parquet_read_count += 1
        columns = list(frame.columns)
        if not REQUIRED_COLUMNS.issubset(set(columns)):
            failures.append("SOURCE_REQUIRED_COLUMNS_MISSING")
            schema_failures += 1
            continue
        if len(frame) != 375:
            failures.append("SOURCE_COMPLETE_SESSION_FAILURE")
            session_failures += 1
        timestamps = _timestamp_local_naive(frame["timestamp"])
        if timestamps is None:
            failures.append("SOURCE_TIMESTAMP_PARSE_FAILURE")
            session_failures += 1
            continue
        if timestamps.nunique() != len(timestamps):
            failures.append("SOURCE_TIMESTAMP_DUPLICATE")
            session_failures += 1
        if not timestamps.is_monotonic_increasing:
            failures.append("SOURCE_TIMESTAMP_MONOTONICITY_FAILURE")
            session_failures += 1
        deltas = timestamps.diff().dropna()
        if len(deltas) and not (deltas == pd.Timedelta(minutes=1)).all():
            failures.append("SOURCE_TIMESTAMP_CADENCE_FAILURE")
            session_failures += 1
        observed_dates = sorted({value.date().isoformat() for value in timestamps})
        session_date = observed_dates[0] if len(observed_dates) == 1 else str(record.get("session_date"))
        if observed_dates == [str(record.get("session_date"))]:
            session_match_count += 1
        else:
            failures.append("SOURCE_SESSION_DATE_MISMATCH")
            session_failures += 1
        timestamp_min = _format_ist_timestamp(timestamps.iloc[0]) if len(timestamps) else ""
        timestamp_max = _format_ist_timestamp(timestamps.iloc[-1]) if len(timestamps) else ""
        expected_start = f"{record.get('session_date')} 09:15"
        expected_end = f"{record.get('session_date')} 15:29"
        if len(timestamps) and (str(timestamps.iloc[0])[:16] != expected_start or str(timestamps.iloc[-1])[:16] != expected_end):
            failures.append("SOURCE_SESSION_BOUNDS_FAILURE")
            session_failures += 1
        normalized_symbols = sorted({_normalize_symbol(value) for value in frame["symbol"].dropna().unique()})
        symbol = normalized_symbols[0] if len(normalized_symbols) == 1 else str(record.get("symbol"))
        if normalized_symbols != [record.get("symbol")]:
            failures.append("SOURCE_SYMBOL_MISMATCH")
            symbol_failures += 1
        finite, positive = _finite_positive_ohlc(frame)
        if not finite:
            failures.append("SOURCE_OHLC_NONFINITE")
            ohlc_failures += 1
        if not positive:
            failures.append("SOURCE_PRICE_NON_POSITIVE")
            ohlc_failures += 1
        if not (frame["high"] >= frame[["open", "close"]].max(axis=1)).all() or not (frame["low"] <= frame[["open", "close"]].min(axis=1)).all():
            failures.append("SOURCE_OHLC_INVALID")
            ohlc_failures += 1

        observed_record = _observed_source_record(
            record_index=index,
            logical_path=logical_path,
            actual_sha256=actual_sha,
            byte_size=byte_size,
            row_count=len(frame),
            columns=columns,
            normalized_symbols=normalized_symbols,
            timestamp_min=timestamp_min,
            timestamp_max=timestamp_max,
            session_date=session_date,
            symbol=symbol,
        )
        metadata_failures = _compare_metadata(record, observed_record)
        failures.extend(metadata_failures)
        if "SOURCE_ACTUAL_SHA_MISMATCH" not in metadata_failures:
            sha_match_count += 1
        if "SOURCE_BYTE_SIZE_MISMATCH" not in metadata_failures:
            byte_size_match_count += 1
        if "SOURCE_ROW_COUNT_METADATA_MISMATCH" not in metadata_failures:
            row_count_match_count += 1
        if "SOURCE_COLUMN_METADATA_MISMATCH" not in metadata_failures:
            schema_match_count += 1
        if "SOURCE_NORMALIZED_SYMBOL_METADATA_MISMATCH" not in metadata_failures and "SOURCE_SYMBOL_METADATA_MISMATCH" not in metadata_failures:
            symbol_match_count += 1
        if "SOURCE_RECORD_ID_MISMATCH" not in metadata_failures:
            record_id_match_count += 1
        if "SOURCE_COLUMN_METADATA_MISMATCH" in metadata_failures:
            schema_failures += 1
        if "SOURCE_NORMALIZED_SYMBOL_METADATA_MISMATCH" in metadata_failures or "SOURCE_SYMBOL_METADATA_MISMATCH" in metadata_failures:
            symbol_failures += 1
        if any(failure.startswith("SOURCE_TIMESTAMP_") for failure in metadata_failures):
            session_failures += 1
        observations.append(
            SourceObservation(
                manifest_index=index,
                manifest_record_id=str(record.get("source_record_id")),
                manifest_symbol=str(record.get("symbol")),
                manifest_session_date=str(record.get("session_date")),
                logical_path=logical_path,
                physical_path=str(resolved),
                actual_sha256=actual_sha,
                byte_size=byte_size,
                observed_record=observed_record,
            )
        )

    duplicate_keys = [key for key, count in Counter((record.get("session_date"), record.get("symbol")) for record in records).items() if count != 1]
    if duplicate_keys:
        failures.append("DUPLICATE_SESSION_SYMBOL_SOURCE")
    if len(set(logical_paths)) != len(logical_paths):
        failures.append("DUPLICATE_LOGICAL_PATH")
    physical_paths = [observation.physical_path for observation in observations]
    actual_hashes = [observation.actual_sha256 for observation in observations]
    if len(set(physical_paths)) != len(physical_paths):
        failures.append("DUPLICATE_PHYSICAL_PATH")
    if len(set(actual_hashes)) != len(actual_hashes):
        failures.append("DUPLICATE_ACTUAL_SHA")
    physical_by_symbol: dict[str, set[str]] = {}
    sha_by_symbol: dict[str, set[str]] = {}
    physical_observations: dict[str, list[dict[str, Any]]] = {}
    sha_observations: dict[str, list[dict[str, Any]]] = {}
    for observation in observations:
        physical_by_symbol.setdefault(observation.physical_path, set()).add(observation.manifest_symbol)
        sha_by_symbol.setdefault(observation.actual_sha256, set()).add(observation.manifest_symbol)
        detail = {
            "record_index": observation.manifest_index,
            "source_record_id": observation.manifest_record_id,
            "symbol": observation.manifest_symbol,
            "session_date": observation.manifest_session_date,
            "logical_path": observation.logical_path,
        }
        physical_observations.setdefault(observation.physical_path, []).append(detail)
        sha_observations.setdefault(observation.actual_sha256, []).append(detail)
    cross_symbol_physical = {path: sorted(symbols) for path, symbols in physical_by_symbol.items() if len(symbols) > 1}
    cross_symbol_sha = {digest: sorted(symbols) for digest, symbols in sha_by_symbol.items() if len(symbols) > 1}
    if cross_symbol_physical:
        failures.append("CROSS_SYMBOL_PHYSICAL_REUSE")
    if cross_symbol_sha:
        failures.append("CROSS_SYMBOL_ACTUAL_SHA_REUSE")

    observed_records = [observation.observed_record for observation in observations]
    observed_order = sorted(observed_records, key=lambda item: (item["symbol"], item["session_date"], item["logical_path"], item["actual_sha256"]))
    observed_order = [{**record, "record_index": index} for index, record in enumerate(observed_order)]
    manifest_payload = _semantic_payload(manifest)
    observed_multiset_equal = Counter(_canonical_json_bytes(record) for record in observed_order) == Counter(
        _canonical_json_bytes(record) for record in manifest_payload
    )
    recomputed_hash = _sha256_bytes(_canonical_json_bytes(observed_order)) if len(observed_order) == len(records) else None
    if recomputed_hash is not None and recomputed_hash != manifest.get("source_manifest_semantic_hash"):
        failures.append("SOURCE_MANIFEST_HASH_MISMATCH")
    if recomputed_hash is not None and not observed_multiset_equal:
        failures.append("SOURCE_MANIFEST_OBSERVED_MULTISET_MISMATCH")

    return {
        "verdict": CERTIFIED if not failures else NOT_CERTIFIED,
        "failures": sorted(set(failures)),
        "record_count": len(records),
        "source_authority_root": str((source_project_root / ALLOWED_SOURCE_ROOT).resolve()) if source_project_root else None,
        "source_authority_failure": authority_failure,
        "source_files_resolved": resolved_count,
        "source_files_byte_probed": byte_probe_count,
        "source_files_parquet_read": parquet_read_count,
        "source_sha_matches": sha_match_count,
        "source_byte_size_matches": byte_size_match_count,
        "source_row_count_matches": row_count_match_count,
        "source_schema_matches": schema_match_count,
        "source_symbol_matches": symbol_match_count,
        "source_session_matches": session_match_count,
        "source_record_id_matches": record_id_match_count,
        "source_root_containment_failures": containment_failures,
        "source_symlink_failures": symlink_failures,
        "complete_session_failures": session_failures,
        "source_session_failures": session_failures,
        "source_symbol_failures": symbol_failures,
        "source_schema_failures": schema_failures,
        "source_ohlc_failures": ohlc_failures,
        "source_uniqueness_failures": len(duplicate_keys)
        + int(len(set(logical_paths)) != len(logical_paths))
        + int(len(set(physical_paths)) != len(physical_paths))
        + int(bool(cross_symbol_physical))
        + int(bool(cross_symbol_sha)),
        "duplicate_session_symbol_keys": [list(key) for key in duplicate_keys],
        "duplicate_logical_path_count": len(logical_paths) - len(set(logical_paths)),
        "duplicate_physical_path_count": len(physical_paths) - len(set(physical_paths)),
        "duplicate_actual_sha_groups": sum(1 for count in Counter(actual_hashes).values() if count > 1),
        "cross_symbol_physical_reuse": cross_symbol_physical,
        "cross_symbol_actual_sha_reuse": cross_symbol_sha,
        "duplicate_physical_path_records": {
            path: details for path, details in physical_observations.items() if len(details) > 1
        },
        "duplicate_actual_sha_records": {
            digest: details for digest, details in sha_observations.items() if len(details) > 1
        },
        "source_manifest_semantic_hash": manifest.get("source_manifest_semantic_hash"),
        "observed_source_semantic_hash": recomputed_hash,
        "source_manifest_semantic_hash_recomputed": recomputed_hash,
        "observed_source_semantic_hash_available": recomputed_hash is not None,
        "source_manifest_semantic_hash_recomputed_available": recomputed_hash is not None,
        "observed_record_count": len(observed_order),
        "manifest_observed_multiset_equal": observed_multiset_equal,
        "independence_boundary": "file_backed_oracle_no_generator_imports",
    }
