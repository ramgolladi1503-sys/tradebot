from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

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


def _contained_path(project_root: Path, logical_path: str) -> tuple[Path | None, str | None]:
    if not logical_path or Path(logical_path).is_absolute():
        return None, "SOURCE_ABSOLUTE_PATH"
    logical = Path(logical_path)
    if any(part == ".." for part in logical.parts):
        return None, "SOURCE_PATH_TRAVERSAL"
    if not logical.parts[: len(ALLOWED_SOURCE_ROOT.parts)] == ALLOWED_SOURCE_ROOT.parts:
        return None, "SOURCE_ROOT_CONTAINMENT_FAILURE"
    candidate = (project_root / logical).resolve()
    allowed = (project_root / ALLOWED_SOURCE_ROOT).resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError:
        return None, "SOURCE_ROOT_CONTAINMENT_FAILURE"
    return candidate, None


def audit_source_manifest_file_backed(manifest: dict[str, Any], *, project_root: Path) -> dict[str, Any]:
    failures: list[str] = []
    records = list(manifest.get("records") or [])
    observed_payload: list[dict[str, Any]] = []
    logical_paths: list[str] = []
    physical_paths: list[str] = []
    actual_hashes: list[str] = []
    byte_probe_count = 0
    session_failures = 0
    containment_failures = 0

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
        resolved, containment_failure = _contained_path(project_root, logical_path)
        if containment_failure:
            failures.append(containment_failure)
            containment_failures += 1
            continue
        if resolved is None or not resolved.exists() or not resolved.is_file():
            failures.append("SOURCE_FILE_MISSING")
            continue
        if resolved.is_symlink():
            failures.append("SOURCE_SYMLINK_ESCAPE")
            containment_failures += 1
            continue
        physical_paths.append(str(resolved))
        actual_sha = _sha256_file(resolved)
        actual_hashes.append(actual_sha)
        byte_probe_count += 1
        if actual_sha != record.get("actual_sha256"):
            failures.append("SOURCE_ACTUAL_SHA_MISMATCH")
        if resolved.stat().st_size != record.get("byte_size"):
            failures.append("SOURCE_BYTE_SIZE_MISMATCH")
        try:
            frame = pd.read_parquet(resolved)
        except Exception:
            failures.append("SOURCE_PARQUET_READ_FAILURE")
            continue
        columns = list(frame.columns)
        if not REQUIRED_COLUMNS.issubset(set(columns)):
            failures.append("SOURCE_REQUIRED_COLUMNS_MISSING")
        if len(frame) != int(record.get("row_count") or -1):
            failures.append("SOURCE_ROW_COUNT_MISMATCH")
        if len(frame) != 375:
            failures.append("SOURCE_COMPLETE_SESSION_FAILURE")
            session_failures += 1
        timestamps = pd.to_datetime(frame["timestamp"], errors="coerce")
        if timestamps.isna().any() or not timestamps.is_monotonic_increasing or timestamps.nunique() != len(timestamps):
            failures.append("SOURCE_TIMESTAMP_SEQUENCE_FAILURE")
            session_failures += 1
        expected_start = f"{record.get('session_date')} 09:15"
        expected_end = f"{record.get('session_date')} 15:29"
        if len(timestamps) and (str(timestamps.iloc[0])[:16] != expected_start or str(timestamps.iloc[-1])[:16] != expected_end):
            failures.append("SOURCE_SESSION_BOUNDS_FAILURE")
            session_failures += 1
        normalized_symbols = sorted({_normalize_symbol(value) for value in frame["symbol"].dropna().unique()})
        if normalized_symbols != [record.get("symbol")]:
            failures.append("SOURCE_SYMBOL_MISMATCH")
        if not (frame["high"] >= frame[["open", "close"]].max(axis=1)).all() or not (frame["low"] <= frame[["open", "close"]].min(axis=1)).all():
            failures.append("SOURCE_OHLC_INVALID")
        if not (frame[["open", "high", "low", "close"]] > 0).all().all():
            failures.append("SOURCE_PRICE_NON_POSITIVE")

        record_id_payload = {
            "actual_sha256": record.get("actual_sha256"),
            "logical_path": logical_path,
            "session_date": record.get("session_date"),
            "symbol": record.get("symbol"),
        }
        if _sha256_bytes(_canonical_json_bytes(record_id_payload)) != record.get("source_record_id"):
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

    recomputed_hash = _sha256_bytes(_canonical_json_bytes(observed_payload if byte_probe_count == len(records) else _semantic_payload(manifest)))
    if recomputed_hash != manifest.get("source_manifest_semantic_hash"):
        failures.append("SOURCE_MANIFEST_HASH_MISMATCH")

    return {
        "verdict": CERTIFIED if not failures else NOT_CERTIFIED,
        "failures": sorted(set(failures)),
        "record_count": len(records),
        "source_files_byte_probed": byte_probe_count,
        "source_root_containment_failures": containment_failures,
        "complete_session_failures": session_failures,
        "source_session_failures": session_failures,
        "source_uniqueness_failures": len(duplicate_keys)
        + int(len(set(logical_paths)) != len(logical_paths))
        + int(len(set(physical_paths)) != len(physical_paths))
        + int(len(set(actual_hashes)) != len(actual_hashes)),
        "source_manifest_semantic_hash_recomputed": recomputed_hash,
        "independence_boundary": "file_backed_oracle_no_generator_imports",
    }
