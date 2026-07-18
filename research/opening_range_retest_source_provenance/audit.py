from __future__ import annotations

# is_order_action=false
# broker_api_called=false

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANIFEST_PATH = PROJECT_ROOT / "docs" / "agent_reviews" / "opening_range_retest_causal_replay_source_manifest_v1.json"
CANDIDATE_LEDGER_PATH = PROJECT_ROOT / "docs" / "agent_reviews" / "opening_range_retest_causal_replay_candidate_ledger_v1.json"
SUMMARY_PATH = PROJECT_ROOT / "docs" / "agent_reviews" / "opening_range_retest_causal_replay_summary_v1.json"
INVENTORY_PATH = PROJECT_ROOT / "docs" / "agent_reviews" / "upstox_corpus_inventory_v2.json"
JSON_OUTPUT_PATH = PROJECT_ROOT / "docs" / "agent_reviews" / "opening_range_retest_source_provenance_audit_v1.json"
MD_OUTPUT_PATH = PROJECT_ROOT / "docs" / "agent_reviews" / "opening_range_retest_source_provenance_audit.md"

EXPECTED_SOURCE_COUNT = 1512
EXPECTED_SOURCE_UNIVERSE_HASH = "cf4cc9cacb2db3a2f9cdc006465ebd5f8af6e6146e6a6a59048e1af38f2393bc"
EXPECTED_CANDIDATE_COUNT = 2215
EXPECTED_CANDIDATE_SEMANTIC_HASH = "53c8cf67f33d1e958bc2ffa1730c00c86d222e67ae76d2e865da6962892e1d24"
EXPECTED_COLUMNS = ("timestamp", "symbol", "open", "high", "low", "close", "volume")
ALLOWED_SYMBOLS = ("BANKNIFTY", "NIFTY", "SENSEX")

CLASSIFICATIONS = (
    "EXACT_MATCH",
    "MANIFEST_SYMBOL_MISMATCH",
    "MANIFEST_PATH_MISMATCH",
    "INVENTORY_SYMBOL_MISMATCH",
    "SOURCE_CONTENT_SYMBOL_MISMATCH",
    "SOURCE_HASH_MISMATCH",
    "SOURCE_SIZE_MISMATCH",
    "SOURCE_ROW_COUNT_MISMATCH",
    "SOURCE_SCHEMA_INVALID",
    "SOURCE_SESSION_INVALID",
    "SOURCE_HISTORY_INVALID",
    "CORRECT_ALTERNATIVE_SOURCE_FOUND",
    "CORRECT_SOURCE_MISSING",
    "AMBIGUOUS_ALTERNATIVE_SOURCES",
    "DUPLICATE_SOURCE_ASSIGNMENT",
    "ALTERNATIVE_FILE_MISSING",
    "ALTERNATIVE_HASH_MISMATCH",
    "ALTERNATIVE_SIZE_MISMATCH",
    "ALTERNATIVE_ROW_COUNT_MISMATCH",
    "ALTERNATIVE_SCHEMA_INVALID",
    "ALTERNATIVE_SESSION_INVALID",
    "ALTERNATIVE_SYMBOL_INVALID",
    "ALTERNATIVE_HISTORY_INVALID",
)


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_symbol(raw: Any) -> str | None:
    text = str(raw or "").strip().upper()
    if not text:
        return None
    if "BANKNIFTY" in text or "NIFTY BANK" in text or "BANK NIFTY" in text or "NIFTYBANK" in text:
        return "BANKNIFTY"
    if "SENSEX" in text:
        return "SENSEX"
    if "NIFTY 50" in text or re.search(r"(^|[^A-Z])NIFTY([^A-Z]|$)", text):
        return "NIFTY"
    return None


def symbol_from_path(path: str | Path) -> str | None:
    stem = Path(str(path)).stem.upper()
    stem = stem.rsplit("_", 1)[0]
    return normalize_symbol(stem)


def session_from_path(path: str | Path) -> str | None:
    match = re.search(r"(20\d{6})", Path(str(path)).name)
    if not match:
        return None
    raw = match.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def manifest_semantic_hash(records: Iterable[dict[str, Any]]) -> str:
    ordered = sorted(
        (dict(record) for record in records),
        key=lambda item: (
            str(item.get("symbol") or ""),
            str(item.get("session_date") or ""),
            str(item.get("logical_path") or ""),
            str(item.get("sha256") or ""),
        ),
    )
    return sha256_bytes(canonical_json_bytes(ordered))


@dataclass(frozen=True)
class SourceProbe:
    exists: bool
    path: str | None = None
    sha256: str | None = None
    byte_size: int | None = None
    row_count: int | None = None
    columns: tuple[str, ...] = ()
    symbol_values: tuple[str, ...] = ()
    normalized_symbols: tuple[str, ...] = ()
    session_dates: tuple[str, ...] = ()
    timestamp_min: str | None = None
    timestamp_max: str | None = None
    schema_error: str | None = None
    history_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "exists": self.exists,
            "path": self.path,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "row_count": self.row_count,
            "columns": list(self.columns),
            "symbol_values": list(self.symbol_values),
            "normalized_symbols": list(self.normalized_symbols),
            "session_dates": list(self.session_dates),
            "timestamp_min": self.timestamp_min,
            "timestamp_max": self.timestamp_max,
            "schema_error": self.schema_error,
            "history_error": self.history_error,
        }


def resolve_source_path(record: dict[str, Any]) -> Path:
    logical = PROJECT_ROOT / str(record.get("logical_path") or "")
    if logical.exists():
        return logical
    return Path(str(record.get("absolute_path") or "")).expanduser()


def probe_source(path: Path) -> SourceProbe:
    if not path.exists():
        return SourceProbe(exists=False, path=str(path))
    sha = sha256_file(path)
    size = path.stat().st_size
    try:
        frame = pd.read_parquet(path, columns=list(EXPECTED_COLUMNS))
    except Exception as exc:  # pragma: no cover - exact parquet engine message is environment-specific
        return SourceProbe(exists=True, path=str(path), sha256=sha, byte_size=size, schema_error=f"{type(exc).__name__}:{exc}")

    columns = tuple(str(column) for column in frame.columns)
    missing = [column for column in EXPECTED_COLUMNS if column not in frame.columns]
    schema_error = f"missing_columns:{','.join(missing)}" if missing else None
    timestamp = pd.to_datetime(frame["timestamp"], errors="coerce") if "timestamp" in frame.columns else pd.Series(dtype="datetime64[ns]")
    history_errors: list[str] = []
    if timestamp.empty or timestamp.isna().any():
        history_errors.append("invalid_timestamp")
    else:
        if any(timestamp.iloc[idx] <= timestamp.iloc[idx - 1] for idx in range(1, len(timestamp))):
            history_errors.append("non_monotonic_timestamp")
        deltas = timestamp.diff().dropna().dt.total_seconds()
        if not deltas.empty and not (deltas == 60).all():
            history_errors.append("non_one_minute_cadence")
    for column in ("open", "high", "low", "close"):
        if column in frame.columns and (pd.to_numeric(frame[column], errors="coerce") <= 0).any():
            history_errors.append(f"non_positive_{column}")
    if {"open", "high", "low", "close"}.issubset(frame.columns):
        high_invalid = frame["high"] < frame[["open", "low", "close"]].max(axis=1)
        low_invalid = frame["low"] > frame[["open", "high", "close"]].min(axis=1)
        if bool(high_invalid.any()):
            history_errors.append("invalid_ohlc_high")
        if bool(low_invalid.any()):
            history_errors.append("invalid_ohlc_low")

    symbols = tuple(sorted({str(value) for value in frame.get("symbol", pd.Series(dtype=object)).dropna().unique()}))
    normalized = tuple(sorted({value for value in (normalize_symbol(symbol) for symbol in symbols) if value}))
    sessions: tuple[str, ...] = ()
    timestamp_min = timestamp_max = None
    if not timestamp.empty and not timestamp.isna().all():
        timestamp_min = timestamp.min().isoformat()
        timestamp_max = timestamp.max().isoformat()
        sessions = tuple(sorted({item.date().isoformat() for item in timestamp.dropna()}))
    return SourceProbe(
        exists=True,
        path=str(path),
        sha256=sha,
        byte_size=size,
        row_count=int(len(frame)),
        columns=columns,
        symbol_values=symbols,
        normalized_symbols=normalized,
        session_dates=sessions,
        timestamp_min=timestamp_min,
        timestamp_max=timestamp_max,
        schema_error=schema_error,
        history_error=";".join(history_errors) if history_errors else None,
    )


def probe_is_valid_for(probe: SourceProbe, *, expected_symbol: str, expected_session: str) -> bool:
    return (
        probe.exists
        and probe.schema_error is None
        and probe.history_error is None
        and probe.row_count == 375
        and expected_session in probe.session_dates
        and tuple([expected_symbol]) == probe.normalized_symbols
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_inventory_rows(path: Path = INVENTORY_PATH) -> dict[str, dict[str, Any]]:
    payload = load_json(path)
    files = payload.get("files") or {}
    return {str(row.get("logical_path") or key): dict(row) for key, row in files.items()}


def candidate_blast_radius(
    ledger: dict[str, Any],
    summary: dict[str, Any],
    defect_keys: set[tuple[str, str]],
    mislabeled_records: list[dict[str, Any]],
) -> dict[str, Any]:
    records = ledger.get("records") or []
    affected_records = [
        record
        for record in records
        if (str(record.get("session_date") or ""), str(record.get("symbol") or "")) in defect_keys
    ]
    unaffected_records = [
        record
        for record in records
        if (str(record.get("session_date") or ""), str(record.get("symbol") or "")) not in defect_keys
    ]
    unaffected_by_symbol = Counter(str(record.get("symbol") or "") for record in unaffected_records)
    unaffected_by_direction = Counter(str(record.get("direction") or "") for record in unaffected_records)
    unaffected_hash = None
    if unaffected_records:
        ordered = sorted((dict(record) for record in unaffected_records), key=lambda entry: canonical_json_bytes(entry).decode("utf-8"))
        unaffected_hash = sha256_bytes(canonical_json_bytes(ordered))
    mislabeled_logical_paths = {str(row.get("logical_path") or "") for row in mislabeled_records}
    defective_profiles = []
    for profile in summary.get("file_profiles") or []:
        profile_path = str(profile.get("path") or "")
        logical_suffix = "runtime/upstox_candidate_replay/"
        logical_path = profile_path[profile_path.index(logical_suffix) :] if logical_suffix in profile_path else profile_path
        if logical_path in mislabeled_logical_paths:
            defective_profiles.append(
                {
                    "logical_path": logical_path,
                    "symbol": profile.get("symbol"),
                    "session_date": profile.get("session_date"),
                    "emission_count": int(profile.get("emission_count") or 0),
                }
            )
    defective_source_candidate_count = sum(int(profile["emission_count"]) for profile in defective_profiles)
    return {
        "ledger_records_available": bool(records),
        "exact_wrong_source_emission_count": defective_source_candidate_count,
        "exact_wrong_source_profiles": defective_profiles,
        "exact_affected_candidate_ids_available": False,
        "exact_affected_candidate_ids": [],
        "exact_candidate_linkage_gap_reason": "Candidate ledger records do not retain source logical_path, so exact source-profile emissions cannot be mapped back to candidate ids.",
        "affected_session_symbol_keys": sorted([list(key) for key in defect_keys]),
        "session_symbol_candidate_upper_bound_count": len(affected_records),
        "session_symbol_candidate_upper_bound_ids": [record.get("setup_id") for record in affected_records],
        "session_symbol_candidate_upper_bound_directions": dict(sorted(Counter(str(record.get("direction") or "") for record in affected_records).items())),
        "session_symbol_candidate_upper_bound_sessions": dict(sorted(Counter(str(record.get("session_date") or "") for record in affected_records).items())),
        "session_symbol_candidate_upper_bound_note": "Upper bound only: these candidates share affected (session, symbol) keys, not proven source logical paths.",
        "unaffected_candidate_count": len(unaffected_records) if records else None,
        "unaffected_candidate_symbols": dict(sorted(unaffected_by_symbol.items())),
        "unaffected_candidate_directions": dict(sorted(unaffected_by_direction.items())),
        "unaffected_subset_semantic_hash": unaffected_hash,
        "corrected_ids_computable": False,
        "candidate_semantic_hash_survives": False,
        "reason": "wrong-symbol source records fed candidate generation; the full candidate semantic hash cannot be reused.",
    }


def sidecar_status(path: Path) -> dict[str, Any]:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    actual = sha256_bytes(path.read_bytes().rstrip(b"\n")) if path.exists() else None
    declared = None
    if sidecar.exists():
        declared = sidecar.read_text(encoding="utf-8").split()[0].strip().lower()
    return {"path": str(path), "sidecar_path": str(sidecar), "actual_sha256": actual, "declared_sha256": declared, "matches": actual == declared}


def _resolve_inventory_path(row: dict[str, Any]) -> Path:
    logical = PROJECT_ROOT / str(row.get("logical_path") or "")
    if logical.exists():
        return logical
    return Path(str(row.get("absolute_path") or "")).expanduser()


def _alternative_failure_classes(
    *,
    probe: SourceProbe,
    row: dict[str, Any],
    expected_symbol: str,
    expected_session: str,
) -> list[str]:
    failures: list[str] = []
    if not probe.exists:
        return ["ALTERNATIVE_FILE_MISSING"]
    if probe.sha256 and probe.sha256 != str(row.get("sha256") or ""):
        failures.append("ALTERNATIVE_HASH_MISMATCH")
    if probe.byte_size is not None and probe.byte_size != int(row.get("byte_size") or 0):
        failures.append("ALTERNATIVE_SIZE_MISMATCH")
    if probe.row_count is not None and probe.row_count != int(row.get("row_count") or 0):
        failures.append("ALTERNATIVE_ROW_COUNT_MISMATCH")
    if probe.schema_error:
        failures.append("ALTERNATIVE_SCHEMA_INVALID")
    if expected_session not in probe.session_dates:
        failures.append("ALTERNATIVE_SESSION_INVALID")
    if tuple([expected_symbol]) != probe.normalized_symbols:
        failures.append("ALTERNATIVE_SYMBOL_INVALID")
    if probe.history_error:
        failures.append("ALTERNATIVE_HISTORY_INVALID")
    return failures


def _alternative_sources(record: dict[str, Any], inventory_rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    session = str(record.get("session_date") or "")
    expected_symbol = str(record.get("symbol") or "")
    alternatives: list[dict[str, Any]] = []
    for logical_path, row in inventory_rows.items():
        if str(row.get("data_role")) != "UNDERLYING_CANDLES":
            continue
        if session_from_path(logical_path) != session:
            continue
        inv_symbols = tuple(sorted({value for value in (normalize_symbol(v) for v in (row.get("symbol_values") or [])) if value}))
        if expected_symbol not in inv_symbols:
            continue
        probe = probe_source(_resolve_inventory_path(row))
        failures = _alternative_failure_classes(probe=probe, row=row, expected_symbol=expected_symbol, expected_session=session)
        alternatives.append(
            {
                "logical_path": logical_path,
                "symbol_values": row.get("symbol_values") or [],
                "normalized_symbols": list(inv_symbols),
                "sha256": row.get("sha256"),
                "row_count": row.get("row_count"),
                "byte_size": row.get("byte_size"),
                "is_current_manifest_path": logical_path == str(record.get("logical_path") or ""),
                "verification": {
                    "passed": not failures,
                    "failures": failures,
                    "source_probe": probe.to_dict(),
                },
            }
        )
    return sorted(alternatives, key=lambda item: str(item["logical_path"]))


def duplicate_identity_groups(records: list[dict[str, Any]], inventory_rows: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    definitions = {
        "duplicate_session_symbol_assignment": lambda item: (item["session_date"], item["symbol"]),
        "duplicate_logical_path": lambda item: (item["logical_path"],),
        "duplicate_resolved_physical_path": lambda item: (str(resolve_source_path(item)),),
        "duplicate_source_sha": lambda item: (item["sha256"],),
        "duplicate_manifest_record_identity": lambda item: (item["session_date"], item["symbol"], item["logical_path"], item["sha256"]),
    }
    groups: dict[str, list[dict[str, Any]]] = {}
    for name, key_fn in definitions.items():
        by_key: dict[tuple[Any, ...], list[tuple[int, dict[str, Any]]]] = {}
        for index, record in enumerate(records):
            by_key.setdefault(key_fn(record), []).append((index, record))
        groups[name] = [
            {
                "identity": list(key),
                "member_record_indexes": [index for index, _ in members],
                "logical_paths": [str(record.get("logical_path") or "") for _, record in members],
                "symbols": [str(record.get("symbol") or "") for _, record in members],
                "sessions": [str(record.get("session_date") or "") for _, record in members],
                "shas": [str(record.get("sha256") or "") for _, record in members],
                "disposition": "duplicate_identity_detected",
            }
            for key, members in sorted(by_key.items())
            if len(members) > 1
        ]
    groups["cross_symbol_logical_path_reuse"] = _cross_symbol_groups(records, lambda item: str(item.get("logical_path") or ""))
    groups["cross_symbol_physical_file_reuse"] = _cross_symbol_groups(records, lambda item: str(resolve_source_path(item)))
    groups["cross_symbol_sha_reuse"] = _cross_symbol_groups(records, lambda item: str(item.get("sha256") or ""))
    inventory_by_identity: dict[tuple[str, str, str], list[str]] = {}
    for key, row in inventory_rows.items():
        identity = (str(row.get("logical_path") or key), str(row.get("sha256") or ""), ",".join(map(str, row.get("symbol_values") or [])))
        inventory_by_identity.setdefault(identity, []).append(key)
    groups["duplicate_inventory_record_identity"] = [
        {"identity": list(identity), "inventory_keys": keys, "disposition": "duplicate_inventory_identity_detected"}
        for identity, keys in sorted(inventory_by_identity.items())
        if len(keys) > 1
    ]
    return groups


def _cross_symbol_groups(records: list[dict[str, Any]], key_fn: Any) -> list[dict[str, Any]]:
    by_key: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, record in enumerate(records):
        by_key.setdefault(key_fn(record), []).append((index, record))
    out: list[dict[str, Any]] = []
    for key, members in sorted(by_key.items()):
        symbols = sorted({str(record.get("symbol") or "") for _, record in members})
        if len(members) > 1 and len(symbols) > 1:
            out.append(
                {
                    "identity": key,
                    "member_record_indexes": [index for index, _ in members],
                    "logical_paths": [str(record.get("logical_path") or "") for _, record in members],
                    "symbols": symbols,
                    "sessions": [str(record.get("session_date") or "") for _, record in members],
                    "shas": [str(record.get("sha256") or "") for _, record in members],
                    "disposition": "cross_symbol_reuse_detected",
                }
            )
    return out


def audit_records(manifest: dict[str, Any], inventory_rows: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    records = manifest.get("records") or []
    duplicate_counts = Counter((str(row.get("session_date") or ""), str(row.get("symbol") or "")) for row in records)
    audited: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for index, record in enumerate(records):
        manifest_symbol = str(record.get("symbol") or "")
        manifest_session = str(record.get("session_date") or "")
        logical_path = str(record.get("logical_path") or "")
        expected_path_symbol = symbol_from_path(logical_path)
        expected_path_session = session_from_path(logical_path)
        inventory = inventory_rows.get(logical_path)
        inventory_symbols = tuple(
            sorted({value for value in (normalize_symbol(v) for v in ((inventory or {}).get("symbol_values") or [])) if value})
        )
        source_path = resolve_source_path(record)
        probe = probe_source(source_path)
        classes: list[str] = []
        if not probe.exists or probe.schema_error:
            classes.append("SOURCE_SCHEMA_INVALID")
        if probe.sha256 and probe.sha256 != str(record.get("sha256") or ""):
            classes.append("SOURCE_HASH_MISMATCH")
        if probe.byte_size is not None and probe.byte_size != int(record.get("byte_size") or 0):
            classes.append("SOURCE_SIZE_MISMATCH")
        if probe.row_count is not None and probe.row_count != int(record.get("row_count") or 0):
            classes.append("SOURCE_ROW_COUNT_MISMATCH")
        if probe.history_error:
            classes.append("SOURCE_HISTORY_INVALID")
        if expected_path_session and expected_path_session != manifest_session:
            classes.append("SOURCE_SESSION_INVALID")
        if probe.session_dates and manifest_session not in probe.session_dates:
            classes.append("SOURCE_SESSION_INVALID")
        if expected_path_symbol and expected_path_symbol != manifest_symbol:
            classes.append("MANIFEST_PATH_MISMATCH")
        if probe.normalized_symbols and tuple([manifest_symbol]) != probe.normalized_symbols:
            classes.append("SOURCE_CONTENT_SYMBOL_MISMATCH")
        if inventory_symbols and tuple([manifest_symbol]) != inventory_symbols:
            classes.append("INVENTORY_SYMBOL_MISMATCH")
        if inventory is None:
            classes.append("CORRECT_SOURCE_MISSING")
        if duplicate_counts[(manifest_session, manifest_symbol)] > 1:
            classes.append("DUPLICATE_SOURCE_ASSIGNMENT")
        alternatives = _alternative_sources(record, inventory_rows)
        non_current = [item for item in alternatives if not item["is_current_manifest_path"]]
        verified_non_current = [item for item in non_current if item["verification"]["passed"]]
        needs_alternative = any(
            item in classes
            for item in (
                "MANIFEST_SYMBOL_MISMATCH",
                "MANIFEST_PATH_MISMATCH",
                "INVENTORY_SYMBOL_MISMATCH",
                "SOURCE_CONTENT_SYMBOL_MISMATCH",
                "SOURCE_HASH_MISMATCH",
                "SOURCE_SIZE_MISMATCH",
                "SOURCE_ROW_COUNT_MISMATCH",
                "SOURCE_SCHEMA_INVALID",
                "SOURCE_SESSION_INVALID",
                "SOURCE_HISTORY_INVALID",
            )
        )
        if needs_alternative:
            for item in non_current:
                classes.extend(item["verification"]["failures"])
            if verified_non_current:
                classes.append("CORRECT_ALTERNATIVE_SOURCE_FOUND" if len(verified_non_current) == 1 else "AMBIGUOUS_ALTERNATIVE_SOURCES")
            elif not alternatives or not verified_non_current:
                classes.append("CORRECT_SOURCE_MISSING")
        if not classes:
            classes.append("EXACT_MATCH")
        for name in sorted(set(classes)):
            counts[name] += 1
        audited.append(
            {
                "record_index": index,
                "session_date": manifest_session,
                "manifest_symbol": manifest_symbol,
                "logical_path": logical_path,
                "absolute_path": record.get("absolute_path"),
                "path_symbol": expected_path_symbol,
                "path_session_date": expected_path_session,
                "inventory_symbol_values": (inventory or {}).get("symbol_values") or [],
                "inventory_normalized_symbols": list(inventory_symbols),
                "source_probe": probe.to_dict(),
                "classifications": sorted(set(classes), key=CLASSIFICATIONS.index),
                "candidate_alternative_sources": non_current,
                "verified_correct_alternative_sources": verified_non_current,
                "manifest_record": record,
            }
        )
    return audited, counts


def derive_root_causes(audited: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in audited:
        if row["classifications"] != ["EXACT_MATCH"]:
            by_date.setdefault(str(row["session_date"]), []).append(row)
    out: dict[str, dict[str, Any]] = {}
    for session, rows in sorted(by_date.items()):
        defective = [
            row
            for row in rows
            if any(
                item in row["classifications"]
                for item in ("MANIFEST_PATH_MISMATCH", "MANIFEST_SYMBOL_MISMATCH", "INVENTORY_SYMBOL_MISMATCH", "SOURCE_CONTENT_SYMBOL_MISMATCH")
            )
        ] or rows
        root_cases = set()
        for row in defective:
            classes = set(row["classifications"])
            if "CORRECT_SOURCE_MISSING" in classes:
                root_cases.add("CORRECT_SOURCE_MISSING")
            if "AMBIGUOUS_ALTERNATIVE_SOURCES" in classes:
                root_cases.add("AMBIGUOUS_CORRECT_SOURCE")
            if "DUPLICATE_SOURCE_ASSIGNMENT" in classes:
                root_cases.add("DUPLICATE_SESSION_SYMBOL_ASSIGNMENT")
            if "MANIFEST_PATH_MISMATCH" in classes:
                root_cases.add("WRONG_MANIFEST_PATH")
            if "MANIFEST_SYMBOL_MISMATCH" in classes:
                root_cases.add("WRONG_MANIFEST_SYMBOL")
            if "INVENTORY_SYMBOL_MISMATCH" in classes:
                root_cases.add("WRONG_INVENTORY_SYMBOL")
            if "SOURCE_CONTENT_SYMBOL_MISMATCH" in classes:
                root_cases.add("WRONG_SOURCE_CONTENT")
        terminal = next(iter(root_cases)) if len(root_cases) == 1 else "MULTIPLE_DEFECTS"
        primary = defective[0]
        alternative = (primary.get("verified_correct_alternative_sources") or [{}])[0]
        out[session] = {
            "terminal_root_cause_case": terminal,
            "derived_cases": sorted(root_cases),
            "defective_manifest_record_indexes": [row["record_index"] for row in defective],
            "defective_logical_paths": [row["logical_path"] for row in defective],
            "defective_manifest_symbols": [row["manifest_symbol"] for row in defective],
            "defective_path_symbols": [row["path_symbol"] for row in defective],
            "defective_inventory_normalized_symbols": [row["inventory_normalized_symbols"] for row in defective],
            "defective_source_content_symbols": [row["source_probe"]["normalized_symbols"] for row in defective],
            "defective_actual_sha256": [row["source_probe"]["sha256"] for row in defective],
            "verified_correct_alternative_logical_path": alternative.get("logical_path"),
            "verified_correct_alternative_sha256": alternative.get("verification", {}).get("source_probe", {}).get("sha256"),
            "verified_correct_alternative_symbol": alternative.get("verification", {}).get("source_probe", {}).get("normalized_symbols"),
            "duplicate_group_members": [
                {"record_index": row["record_index"], "logical_path": row["logical_path"], "symbol": row["manifest_symbol"]}
                for row in rows
                if "DUPLICATE_SOURCE_ASSIGNMENT" in row["classifications"]
            ],
            "reason": "Derived from manifest/path, inventory, byte-probed source content, verified alternatives, and duplicate assignment classifications.",
        }
    return out


def build_audit_payload() -> dict[str, Any]:
    manifest = load_json(SOURCE_MANIFEST_PATH)
    ledger = load_json(CANDIDATE_LEDGER_PATH)
    summary = load_json(SUMMARY_PATH)
    inventory_rows = load_inventory_rows()
    audited, counts = audit_records(manifest, inventory_rows)
    duplicate_groups = duplicate_identity_groups(manifest.get("records") or [], inventory_rows)
    defect_records = [row for row in audited if row["classifications"] != ["EXACT_MATCH"]]
    mislabeled_records = [
        row
        for row in audited
        if any(
            name in row["classifications"]
            for name in ("MANIFEST_PATH_MISMATCH", "INVENTORY_SYMBOL_MISMATCH", "SOURCE_CONTENT_SYMBOL_MISMATCH")
        )
    ]
    duplicate_contaminated_records = [row for row in audited if "DUPLICATE_SOURCE_ASSIGNMENT" in row["classifications"]]
    defect_keys = {(row["session_date"], row["manifest_symbol"]) for row in defect_records}
    recomputed_source_hash = manifest_semantic_hash(manifest.get("records") or [])
    decision = "ORB_PHASE1_INVALID" if defect_records else "READY"
    reason = (
        "ORB Phase 1 source manifest has verified source identity defects; v1 source and candidate hashes cannot certify Phase 1."
        if defect_records
        else "all source records exact-match"
    )
    payload = {
        "schema_version": 1,
        "mode": "RESEARCH_ORB_PHASE1_SOURCE_PROVENANCE_AUDIT",
        "candidate_id": "opening_range_retest_source_provenance_audit_v1",
        "decision": decision,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "source": "docs/agent_reviews/opening_range_retest_source_provenance_audit_v1.json",
        "allowed_for_live_execution": False,
        "production_files_touched": [],
        "source_data_files_mutated": [],
        "expected_invariants": {
            "selected_source_count": EXPECTED_SOURCE_COUNT,
            "source_universe_hash": EXPECTED_SOURCE_UNIVERSE_HASH,
            "candidate_count": EXPECTED_CANDIDATE_COUNT,
            "candidate_semantic_hash": EXPECTED_CANDIDATE_SEMANTIC_HASH,
        },
        "observed_invariants": {
            "selected_source_count": len(manifest.get("records") or []),
            "manifest_declared_source_universe_hash": (manifest.get("selection_summary") or {}).get("semantic_hash"),
            "recomputed_manifest_semantic_hash": recomputed_source_hash,
            "candidate_count": ledger.get("candidate_count"),
            "candidate_semantic_hash": ledger.get("candidate_semantic_hash"),
            "source_sidecar_status": sidecar_status(SOURCE_MANIFEST_PATH),
            "candidate_ledger_sidecar_status": sidecar_status(CANDIDATE_LEDGER_PATH),
        },
        "classification_counts": dict(sorted(counts.items())),
        "records_audited": len(audited),
        "defective_source_record_count": len(defect_records),
        "mislabeled_source_record_count": len(mislabeled_records),
        "duplicate_contaminated_source_record_count": len(duplicate_contaminated_records),
        "exact_match_count": counts.get("EXACT_MATCH", 0),
        "verified_correct_alternative_count": counts.get("CORRECT_ALTERNATIVE_SOURCE_FOUND", 0),
        "ambiguous_alternative_count": counts.get("AMBIGUOUS_ALTERNATIVE_SOURCES", 0),
        "missing_correct_source_count": counts.get("CORRECT_SOURCE_MISSING", 0),
        "affected_session_symbol_count": len(defect_keys),
        "affected_session_symbol_keys": sorted([list(key) for key in defect_keys]),
        "root_cause_by_affected_date": derive_root_causes(audited),
        "duplicate_identity_audit": {
            "definitions": {
                "duplicate_session_symbol_assignment": ["session_date", "symbol"],
                "duplicate_logical_path": ["logical_path"],
                "duplicate_resolved_physical_path": ["resolved physical path"],
                "duplicate_source_sha": ["sha256"],
                "cross_symbol_logical_path_reuse": ["logical_path reused across symbols"],
                "cross_symbol_physical_file_reuse": ["resolved physical path reused across symbols"],
                "cross_symbol_sha_reuse": ["sha256 reused across symbols"],
                "duplicate_manifest_record_identity": ["session_date", "symbol", "logical_path", "sha256"],
                "duplicate_inventory_record_identity": ["logical_path", "sha256", "symbol_values"],
            },
            "groups": duplicate_groups,
            "counts": {name: len(groups) for name, groups in sorted(duplicate_groups.items())},
            "record_counts": {
                name: sum(len(group.get("member_record_indexes", [])) for group in groups)
                for name, groups in sorted(duplicate_groups.items())
            },
        },
        "candidate_blast_radius": candidate_blast_radius(ledger, summary, defect_keys, mislabeled_records),
        "records": audited,
    }
    payload["observed_invariants"]["source_count_matches_expected"] = payload["observed_invariants"]["selected_source_count"] == EXPECTED_SOURCE_COUNT
    payload["observed_invariants"]["source_hash_matches_expected"] = (
        payload["observed_invariants"]["manifest_declared_source_universe_hash"] == EXPECTED_SOURCE_UNIVERSE_HASH
        and recomputed_source_hash == EXPECTED_SOURCE_UNIVERSE_HASH
    )
    payload["observed_invariants"]["candidate_count_matches_expected"] = ledger.get("candidate_count") == EXPECTED_CANDIDATE_COUNT
    payload["observed_invariants"]["candidate_hash_matches_expected"] = ledger.get("candidate_semantic_hash") == EXPECTED_CANDIDATE_SEMANTIC_HASH
    return payload


def write_outputs(payload: dict[str, Any], *, json_path: Path = JSON_OUTPUT_PATH, md_path: Path = MD_OUTPUT_PATH) -> str:
    serialized = canonical_json_bytes(payload)
    json_path.write_bytes(serialized + b"\n")
    digest = sha256_bytes(serialized)
    json_path.with_suffix(json_path.suffix + ".sha256").write_text(f"{digest}  {json_path.name}\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload, digest), encoding="utf-8")
    return digest


def render_markdown(payload: dict[str, Any], digest: str) -> str:
    counts = payload["classification_counts"]
    blast = payload["candidate_blast_radius"]
    def evidence_line(name: str, value: Any) -> str:
        if isinstance(value, bool):
            value = str(value).lower()
        return f"- {name}: {value}"

    return "\n".join(
        [
            "# ORB Phase 1 Source Provenance Audit v1",
            "",
            "## Agent Work Contract",
            f"- mode: {payload['mode']}",
            f"- candidate_id: {payload['candidate_id']}",
            f"- decision: {payload['decision']}",
            f"- reason: {payload['reason']}",
            f"- timestamp: {payload['timestamp']}",
            evidence_line("is_order_action", payload["is_order_action"]),
            evidence_line("broker_api_called", payload["broker_api_called"]),
            f"- source: {payload['source']}",
            "- source_agent: Codex",
            "- action: READ_ONLY_SOURCE_PROVENANCE_AUDIT",
            "- title: ORB Phase 1 source-provenance repair and blast-radius certification",
            "- scope: docs/research/source-provenance audit only",
            "- requested_paths: research/opening_range_retest_source_provenance/, scripts/audit_opening_range_retest_source_provenance.py, tests/test_opening_range_retest_source_provenance.py, docs/agent_reviews/opening_range_retest_source_provenance_audit*",
            "- allowed_paths: research/opening_range_retest_source_provenance/, scripts/audit_opening_range_retest_source_provenance.py, tests/test_opening_range_retest_source_provenance.py, docs/agent_reviews/",
            "- forbidden_paths: strategies/, core/, config/, broker/execution/risk/feed paths, runtime source parquet, credentials, main.py, run_live.sh",
            "- expected_tests: pytest, py_compile, ruff, evidence gate",
            "- acceptance_proof: JSON audit, SHA-256 sidecar, and this markdown report",
            "",
            "## Scope Guard",
            "- read_only=true",
            "- append=false",
            "- is_order_action=false",
            "- broker_api_called=false",
            "- allowed_for_live_execution=false",
            "- PRODUCTION FILES TOUCHED: NONE",
            "- SOURCE DATA FILES MUTATED: NONE",
            "",
            "## Grill Me Review",
            "- Verdict: PASS for failing closed. The audit found source identity contradictions, so Phase 1 outcome certification must not continue from the challenged artifacts.",
            f"- Defective source records: {payload['defective_source_record_count']}",
            f"- Mislabeled source records: {payload['mislabeled_source_record_count']}",
            f"- Duplicate-contaminated source records: {payload['duplicate_contaminated_source_record_count']}",
            f"- Affected session/symbol keys: {payload['affected_session_symbol_keys']}",
            "",
            "## Hermes Review",
            "- The repair path is a separate provenance-audit artifact, not silent mutation of v1 replay outputs.",
            "- Source roots are treated as mutable local paths; immutable identity comes from logical path, session, symbol, size, row count, and SHA-256.",
            "",
            "## GSD Review",
            f"- JSON artifact SHA-256: `{digest}`",
            f"- Decision: `{payload['decision']}`",
            f"- Classification counts: `{json.dumps(counts, sort_keys=True)}`",
            "",
            "## QA / Safety Review",
            "- The auditor reads all manifest records and continues after per-record failures.",
            "- It checks manifest path identity, inventory symbol identity, file content symbol identity, size, row count, hash, schema, session, history, duplicate assignments, and alternatives.",
            "",
            "## Acceptance Proof",
            f"- records_audited: {payload['records_audited']}",
            f"- selected source count observed: {payload['observed_invariants']['selected_source_count']}",
            f"- source-universe hash observed: `{payload['observed_invariants']['recomputed_manifest_semantic_hash']}`",
            f"- candidate count observed: {payload['observed_invariants']['candidate_count']}",
            f"- candidate semantic hash observed: `{payload['observed_invariants']['candidate_semantic_hash']}`",
            f"- exact_wrong_source_emission_count: {blast['exact_wrong_source_emission_count']}",
            f"- session_symbol_candidate_upper_bound_count: {blast['session_symbol_candidate_upper_bound_count']}",
            f"- exact_affected_candidate_ids_available: {str(blast['exact_affected_candidate_ids_available']).lower()}",
            f"- unaffected_candidate_count: {blast['unaffected_candidate_count']}",
            f"- unaffected_subset_semantic_hash: `{blast['unaffected_subset_semantic_hash']}`",
            "",
            "## Runtime Proof Required After Merge",
            "- No runtime proof is claimed by this PR.",
            "- If source provenance is corrected later, rerun the ORB Phase 1 replay and independent audit from exact merged main before making outcome claims.",
            "",
            "## What This PR Does Not Prove",
            "- It does not prove ORB profitability, fills, live readiness, broker behavior, paper readiness, or corrected candidate outcomes.",
            "- It does not mutate source data or certify PR #674 outcome artifacts.",
            "",
            "## Human Approval",
            "- Required before any future source substitution, v2 replay recertification, or outcome claim restoration.",
            "",
            "## Final Verdict",
            f"`{payload['decision']}`",
            "",
        ]
    )


def main() -> int:
    payload = build_audit_payload()
    write_outputs(payload)
    print(
        json.dumps(
            {
                "cli_exit_contract": {
                    "0": "no provenance defects",
                    "1": "auditor execution/configuration failure",
                    "2": "provenance audit completed and found invalid certification",
                },
                "cli_verdict": "AUDIT_INVALID" if payload["decision"] != "READY" else "READY",
                "decision": payload["decision"],
                "records_audited": payload["records_audited"],
                "defective_source_record_count": payload["defective_source_record_count"],
            },
            sort_keys=True,
        )
    )
    return 0 if payload["decision"] == "READY" else 2
