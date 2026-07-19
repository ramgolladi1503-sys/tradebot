from __future__ import annotations

import hashlib
import json
from collections import Counter
from math import isfinite
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype

ALLOWED_SOURCE_ROOT = Path("runtime/upstox_candidate_replay")
REQUIRED_COLUMNS = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
CERTIFIED = "ORB_PHASE1_V2_SOURCE_MANIFEST_CERTIFIED"
NOT_CERTIFIED = "ORB_PHASE1_V2_SOURCE_MANIFEST_NOT_CERTIFIED"


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


def audit_source_manifest_file_backed(
    manifest: dict[str, Any], *, source_project_root: Path | None
) -> dict[str, Any]:
    failures: list[str] = []
    records = list(manifest.get("records") or [])
    observed_payload: list[dict[str, Any]] = []
    logical_paths: list[str] = []
    physical_paths: list[str] = []
    actual_hashes: list[str] = []
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
        physical_paths.append(str(resolved))
        actual_sha = _sha256_file(resolved)
        actual_hashes.append(actual_sha)
        byte_probe_count += 1
        if actual_sha == record.get("actual_sha256"):
            sha_match_count += 1
        else:
            failures.append("SOURCE_ACTUAL_SHA_MISMATCH")
        if resolved.stat().st_size == record.get("byte_size"):
            byte_size_match_count += 1
        else:
            failures.append("SOURCE_BYTE_SIZE_MISMATCH")
        try:
            frame = pd.read_parquet(resolved)
        except Exception:
            failures.append("SOURCE_PARQUET_READ_FAILURE")
            continue
        parquet_read_count += 1
        columns = list(frame.columns)
        if REQUIRED_COLUMNS.issubset(set(columns)):
            schema_match_count += 1
        else:
            failures.append("SOURCE_REQUIRED_COLUMNS_MISSING")
            schema_failures += 1
            continue
        if len(frame) == int(record.get("row_count") or -1):
            row_count_match_count += 1
        else:
            failures.append("SOURCE_ROW_COUNT_MISMATCH")
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
        if observed_dates == [str(record.get("session_date"))]:
            session_match_count += 1
        else:
            failures.append("SOURCE_SESSION_DATE_MISMATCH")
            session_failures += 1
        if str(record.get("timestamp_min")) != f"{record.get('session_date')}T09:15:00+05:30":
            failures.append("SOURCE_TIMESTAMP_METADATA_MISMATCH")
            failures.append("SOURCE_TIMESTAMP_SEQUENCE_FAILURE")
            session_failures += 1
        expected_start = f"{record.get('session_date')} 09:15"
        expected_end = f"{record.get('session_date')} 15:29"
        if len(timestamps) and (str(timestamps.iloc[0])[:16] != expected_start or str(timestamps.iloc[-1])[:16] != expected_end):
            failures.append("SOURCE_SESSION_BOUNDS_FAILURE")
            session_failures += 1
        normalized_symbols = sorted({_normalize_symbol(value) for value in frame["symbol"].dropna().unique()})
        if normalized_symbols == [record.get("symbol")] and record.get("normalized_source_symbols") == normalized_symbols:
            symbol_match_count += 1
        else:
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

        record_id_payload = {
            "actual_sha256": record.get("actual_sha256"),
            "logical_path": logical_path,
            "session_date": record.get("session_date"),
            "symbol": record.get("symbol"),
        }
        if _sha256_bytes(_canonical_json_bytes(record_id_payload)) == record.get("source_record_id"):
            record_id_match_count += 1
        else:
            failures.append("SOURCE_RECORD_ID_MISMATCH")
        observed_payload.append({key: value for key, value in record.items() if key != "diagnostic_absolute_path"})
        if record.get("record_index") != index:
            failures.append("SOURCE_RECORD_INDEX_MISMATCH")

    duplicate_keys = [key for key, count in Counter((record.get("session_date"), record.get("symbol")) for record in records).items() if count != 1]
    if duplicate_keys:
        failures.append("DUPLICATE_SESSION_SYMBOL_SOURCE")
    if len(set(logical_paths)) != len(logical_paths):
        failures.append("DUPLICATE_LOGICAL_PATH")
    if len(set(physical_paths)) != len(physical_paths):
        failures.append("DUPLICATE_PHYSICAL_PATH")
    if len(set(actual_hashes)) != len(actual_hashes):
        failures.append("DUPLICATE_ACTUAL_SHA")
    physical_by_symbol: dict[str, set[str]] = {}
    sha_by_symbol: dict[str, set[str]] = {}
    for record, physical_path, actual_sha in zip(records, physical_paths, actual_hashes, strict=False):
        physical_by_symbol.setdefault(physical_path, set()).add(str(record.get("symbol")))
        sha_by_symbol.setdefault(actual_sha, set()).add(str(record.get("symbol")))
    cross_symbol_physical = {path: sorted(symbols) for path, symbols in physical_by_symbol.items() if len(symbols) > 1}
    cross_symbol_sha = {digest: sorted(symbols) for digest, symbols in sha_by_symbol.items() if len(symbols) > 1}
    if cross_symbol_physical:
        failures.append("CROSS_SYMBOL_PHYSICAL_REUSE")
    if cross_symbol_sha:
        failures.append("CROSS_SYMBOL_ACTUAL_SHA_REUSE")

    recomputed_hash = _sha256_bytes(_canonical_json_bytes(observed_payload)) if byte_probe_count == len(records) else None
    if recomputed_hash is not None and recomputed_hash != manifest.get("source_manifest_semantic_hash"):
        failures.append("SOURCE_MANIFEST_HASH_MISMATCH")

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
        "source_manifest_semantic_hash_recomputed": recomputed_hash,
        "source_manifest_semantic_hash_recomputed_available": recomputed_hash is not None,
        "independence_boundary": "file_backed_oracle_no_generator_imports",
    }
