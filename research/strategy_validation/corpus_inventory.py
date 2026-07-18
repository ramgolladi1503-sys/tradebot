from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .data_suitability import (
    DatasetInspection,
    _current_git_commit,
    _default_bundle_path,
    _source_root_label,
    inspect_dataset,
    load_frozen_contract_bundle,
    sha256_file,
)

CORPUS_INVENTORY_SCHEMA_VERSION = 1
DEFAULT_FETCH_MANIFEST_PREFIX = "upstox_fetch_manifest_"
DEFAULT_CAPTURE_MANIFEST_PREFIX = "upstox_capture_manifest_"
DEFAULT_CACHE_FILENAMES = {".DS_Store"}
DEFAULT_CACHE_PREFIXES = {"._"}
DEFAULT_NON_SOURCE_DIR_NAMES = {"__pycache__"}
DEFAULT_DATASET_SUFFIXES = {".parquet", ".csv", ".json", ".jsonl", ".db", ".sqlite", ".sqlite3"}
_CANONICAL_PATH_PATTERNS = (
    re.compile(r"(runtime/upstox_candidate_replay/.*)$"),
    re.compile(r"(\.runtime/market_data/.*)$"),
    re.compile(r"(\d{8}/(?:underlying|options|manifests)/.*)$"),
    re.compile(r"((?:underlying|options|manifests)/.*)$"),
)


@dataclass(frozen=True)
class CorpusFileRecord:
    absolute_path: str
    logical_path: str
    source_root: str
    file_role: str
    data_role: str
    file_format: str
    file_size_bytes: int
    sha256: str
    row_count: int | None
    schema_columns: tuple[dict[str, str], ...]
    timestamp_field: str | None
    timestamp_timezone: str | None
    timestamp_min: str | None
    timestamp_max: str | None
    symbol_values: tuple[str, ...]
    instrument_tokens: tuple[str, ...]
    bar_interval: str | None
    duplicate_rows_exact: int | None
    duplicate_rows_natural_key: int | None
    null_counts: dict[str, int]
    volume_sum: float | None
    volume_nonzero_rows: int | None
    volume_truth_status: str
    data_kind: str
    provenance: str
    session_integrity: dict[str, Any] | None
    inspection_error: str
    quality_status: str
    accepted_for_snapshot: bool
    diff_status: str
    diff_classification: str
    exclusion_reason: str
    reconciliation_status: str | None = None


@dataclass(frozen=True)
class FetchManifestRecord:
    absolute_path: str
    logical_path: str
    date: str | None
    requested_instruments: tuple[str, ...]
    requested_interval: str | None
    fetch_status: str
    http_result: str
    returned_rows: int | None
    output_paths: tuple[str, ...]
    output_hashes: tuple[str, ...]
    retry_count: int | None
    error_classification: str
    reconciliation_status: str
    manifest_payload: dict[str, Any]


@dataclass(frozen=True)
class SourceRootRecord:
    requested_path: str
    expanded_path: str
    resolved_path: str
    exists: bool
    is_directory: bool
    is_symlink: bool
    readable: bool
    source_role: str
    file_count: int
    accepted_file_count: int
    rejected_file_count: int
    root_status: str


@dataclass(frozen=True)
class DatasetFamily:
    family_id: str
    data_role: str
    component_file_hashes: tuple[str, ...]
    component_logical_paths: tuple[str, ...]
    underlying_identity: str | None
    symbol: str | None
    exchange: str | None
    session_dates: tuple[str, ...]
    bar_interval: str | None
    timezone: str | None
    expiry_coverage: tuple[str, ...]
    strike_coverage: tuple[str, ...]
    option_type_coverage: tuple[str, ...]
    schema: tuple[dict[str, str], ...]
    timestamp_range: tuple[str | None, str | None]
    file_count: int


@dataclass(frozen=True)
class JoinabilityRecord:
    left_family_id: str
    right_family_id: str
    classification: str
    reason: str
    join_direction: str
    maximum_tolerance_seconds: int | None
    tie_behavior: str | None
    missing_match_behavior: str


@dataclass(frozen=True)
class CompositeCorpus:
    composite_id: str
    replay_type: str
    strategy_id: str
    component_family_ids: tuple[str, ...]
    component_file_hashes: tuple[str, ...]
    underlying_identity: str | None
    session_range: tuple[str | None, str | None]
    timezone: str | None
    bar_interval: str | None
    join_policy: str
    timestamp_tolerance_seconds: int | None
    instrument_resolution_policy: str
    direct_fields: tuple[str, ...]
    derived_fields: tuple[str, ...]
    provenance_limitations: tuple[str, ...]
    signal_suitability: str
    execution_suitability: str
    blockers: tuple[str, ...]


def default_inventory_source_roots() -> tuple[Path, ...]:
    shared_root = Path("/Users/madhuram/tradebot")
    root = shared_root if shared_root.exists() else Path(__file__).resolve().parents[2]
    return (
        root / "runtime" / "upstox_candidate_replay",
        root / ".runtime" / "market_data",
    )


def _expand_requested_root(root: Path | str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(root))))


def _source_root_role(path: Path) -> str:
    text = str(path).replace("\\", "/").lower()
    if "upstox_candidate_replay" in text:
        return "HISTORICAL_CANDIDATE_REPLAY"
    if ".runtime/market_data" in text:
        return "MARKET_DATA"
    if "runtime/market_data" in text:
        return "MARKET_DATA"
    return "UNKNOWN"


def _root_status(*, exists: bool, readable: bool, is_directory: bool, file_count: int, accepted_file_count: int) -> str:
    if not exists:
        return "MISSING"
    if not readable:
        return "UNREADABLE"
    if not is_directory:
        return "INVALID"
    if file_count == 0:
        return "EMPTY"
    if accepted_file_count > 0:
        return "AVAILABLE_WITH_DATA"
    return "AVAILABLE"


def _preflight_root_status(*, exists: bool, readable: bool, is_directory: bool) -> str:
    if not exists:
        return "MISSING"
    if not readable:
        return "UNREADABLE"
    if not is_directory:
        return "INVALID"
    return "AVAILABLE"


def _source_root_record(
    path: Path,
    *,
    file_count: int = 0,
    accepted_file_count: int = 0,
    finalize: bool = True,
) -> SourceRootRecord:
    expanded = _expand_requested_root(path)
    exists = expanded.exists()
    is_directory = expanded.is_dir()
    readable = os.access(expanded, os.R_OK) if exists else False
    is_symlink = expanded.is_symlink()
    resolved = str(expanded.resolve(strict=False))
    rejected = max(int(file_count) - int(accepted_file_count), 0)
    root_status = _root_status(
        exists=exists,
        readable=readable,
        is_directory=is_directory,
        file_count=int(file_count),
        accepted_file_count=int(accepted_file_count),
    ) if finalize else _preflight_root_status(exists=exists, readable=readable, is_directory=is_directory)
    return SourceRootRecord(
        requested_path=str(path),
        expanded_path=str(expanded),
        resolved_path=resolved,
        exists=exists,
        is_directory=is_directory,
        is_symlink=is_symlink,
        readable=readable,
        source_role=_source_root_role(expanded),
        file_count=int(file_count),
        accepted_file_count=int(accepted_file_count),
        rejected_file_count=int(rejected),
        root_status=root_status,
    )


def _audit_source_roots(
    requested_roots: Iterable[Path] | None,
    records: list[CorpusFileRecord] | None = None,
    *,
    finalize: bool = True,
) -> tuple[list[SourceRootRecord], list[Path]]:
    requested = [Path(root) for root in (requested_roots or default_inventory_source_roots())]
    audited: list[SourceRootRecord] = []
    active_roots: list[Path] = []
    records = list(records or [])
    for root in requested:
        expanded = _expand_requested_root(root)
        exists = expanded.exists()
        readable = os.access(expanded, os.R_OK) if exists else False
        is_directory = expanded.is_dir()
        if exists and readable and is_directory:
            active_roots.append(expanded)
        matching = [record for record in records if _expanded_root_contains(expanded, record.absolute_path)]
        accepted = sum(1 for record in matching if record.accepted_for_snapshot)
        audited.append(
            _source_root_record(
                root,
                file_count=len(matching),
                accepted_file_count=accepted,
                finalize=finalize,
            )
        )
    return audited, active_roots


def _expanded_root_contains(root: Path, absolute_path: str) -> bool:
    try:
        Path(absolute_path).resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _hidden_or_cache_file(path: Path) -> bool:
    name = path.name
    return name in DEFAULT_CACHE_FILENAMES or any(name.startswith(prefix) for prefix in DEFAULT_CACHE_PREFIXES)


def _is_supported_dataset_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in DEFAULT_DATASET_SUFFIXES


def _is_manifest_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".json" and (
        path.name.startswith(DEFAULT_FETCH_MANIFEST_PREFIX) or path.name.startswith(DEFAULT_CAPTURE_MANIFEST_PREFIX)
    )


def discover_inventory_files(roots: Iterable[Path] | None = None) -> list[Path]:
    discovered: list[Path] = []
    seen: set[Path] = set()
    for root in roots or default_inventory_source_roots():
        root = Path(root)
        if not root.exists():
            continue
        if root.is_file():
            candidates = [root]
        else:
            candidates = sorted(
                path
                for path in root.rglob("*")
                if path.is_file() and not any(part in DEFAULT_NON_SOURCE_DIR_NAMES for part in path.parts)
            )
        for path in candidates:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            discovered.append(path)
    return sorted(discovered, key=lambda p: str(p))


def _canonical_logical_path_text(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    for pattern in _CANONICAL_PATH_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return text.lstrip("./")


def _canonical_logical_path(path: Path) -> str:
    return _canonical_logical_path_text(path)


def _canonical_source_role(item: Mapping[str, Any]) -> str:
    role = str(item.get("data_role") or item.get("file_role") or item.get("source_category") or item.get("data_kind") or "")
    role = role.upper()
    if role.startswith("UNDERLYING_CANDLES") or role.startswith("CANDLE"):
        return "UNDERLYING_CANDLES"
    if role.startswith("UNDERLYING_TICKS") or role.startswith("TICK_STREAM"):
        return "UNDERLYING_TICKS"
    if role.startswith("OPTION_DEPTH") or role.startswith("TICK_WITH_DEPTH"):
        return "OPTION_DEPTH" if _looks_like_option_symbol(str(item.get("symbol") or "")) else "UNDERLYING_TICKS"
    if role.startswith("OPTION_QUOTES") or role.startswith("TICK_QUOTE"):
        return "OPTION_QUOTES" if _looks_like_option_symbol(str(item.get("symbol") or "")) else "UNDERLYING_TICKS"
    if role.startswith("OPTION_LTP") or role.startswith("LTP_ONLY"):
        return "OPTION_LTP" if _looks_like_option_symbol(str(item.get("symbol") or "")) else "UNDERLYING_TICKS"
    if "MANIFEST" in role:
        return "MANIFEST"
    logical_path = _canonical_logical_path_text(item.get("relative_path") or item.get("absolute_path") or item.get("logical_path") or "")
    if "manifests/" in logical_path:
        return "MANIFEST"
    if "options/" in logical_path:
        return "OPTION_QUOTES" if "_depth" not in logical_path.lower() else "OPTION_DEPTH"
    if "market_data/" in logical_path:
        return "UNDERLYING_TICKS"
    if "underlying/" in logical_path:
        return "UNDERLYING_CANDLES"
    return "UNKNOWN"


def _canonical_comparison_record(item: Mapping[str, Any]) -> dict[str, Any]:
    logical_path = _canonical_logical_path_text(item.get("relative_path") or item.get("absolute_path") or item.get("logical_path") or "")
    content_sha256 = str(item.get("sha256") or "")
    byte_size = int(item.get("file_size_bytes") or item.get("byte_size") or 0)
    source_role = _canonical_source_role(item)
    return {
        "logical_source_role": source_role,
        "normalized_relative_path": logical_path,
        "content_sha256": content_sha256,
        "byte_size": byte_size,
        "quality_status": str(item.get("quality_status") or item.get("suitability_status") or ""),
        "data_kind": str(item.get("data_kind") or ""),
        "file_format": str(item.get("file_format") or ""),
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _snapshot_digest(entries: list[dict[str, Any]]) -> str:
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=_json_default)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _role_for_dataset(path: Path, inspection: DatasetInspection) -> str:
    path_text = str(path).lower()
    columns = {item["name"].lower() for item in inspection.schema_columns}
    symbols = [str(item).upper() for item in inspection.symbol_values]
    looks_like_option = any(_looks_like_option_symbol(symbol) for symbol in symbols) or "option" in path_text
    if inspection.data_kind.startswith("CANDLE"):
        return "UNDERLYING_CANDLES"
    if inspection.data_kind == "TICK_WITH_DEPTH":
        return "OPTION_DEPTH" if looks_like_option or any("expiry" in col for col in columns) else "UNDERLYING_TICKS"
    if inspection.data_kind == "TICK_QUOTE":
        if looks_like_option or any(name in columns for name in ("expiry", "strike", "option_type", "optiontype")):
            return "OPTION_QUOTES"
        return "UNDERLYING_TICKS"
    if inspection.data_kind == "TICK_STREAM":
        return "UNDERLYING_TICKS"
    if inspection.data_kind == "LTP_ONLY":
        return "OPTION_LTP" if looks_like_option else "UNDERLYING_TICKS"
    return "UNKNOWN"


def _looks_like_option_symbol(symbol: str) -> bool:
    upper = symbol.upper()
    return any(token in upper for token in (" CE ", " PE ", " CALL", " PUT", "OPT", "OPTION")) and any(
        char.isdigit() for char in upper
    )


def _category_for_path(path: Path) -> str:
    name = path.name
    if _hidden_or_cache_file(path):
        return "TEMPORARY_OR_CACHE_FILE"
    if name.startswith(DEFAULT_FETCH_MANIFEST_PREFIX):
        return "FETCH_MANIFEST"
    if name.startswith(DEFAULT_CAPTURE_MANIFEST_PREFIX):
        return "CAPTURE_MANIFEST"
    if path.suffix.lower() == ".jsonl" and path.stat().st_size == 0:
        return "PRESENCE_MARKER"
    if _is_supported_dataset_file(path):
        return "MARKET_DATA"
    return "UNKNOWN_ARTIFACT"


def _parse_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _infer_manifest_requested_interval(manifest: Mapping[str, Any], outputs: list[dict[str, Any]]) -> str | None:
    for key in ("interval", "requested_interval", "bar_interval"):
        value = manifest.get(key)
        if value:
            return str(value)
    for output in outputs:
        interval = output.get("bar_interval")
        if interval:
            return str(interval)
    return None


def _infer_manifest_requested_instruments(outputs: list[dict[str, Any]]) -> tuple[str, ...]:
    values: list[str] = []
    for output in outputs:
        values.extend(output.get("symbol_values", ()))
    return tuple(sorted(dict.fromkeys(values)))


def _manifest_output_paths(path: Path, manifest: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    date = str(manifest.get("date") or "").strip()
    if not date:
        return ()
    output_dir = path.parent.parent / "underlying"
    if not output_dir.exists():
        return ()
    outputs: list[dict[str, Any]] = []
    for candidate in sorted(output_dir.glob(f"*_{date}.parquet")):
        try:
            inspection = inspect_dataset(candidate, bundle=load_frozen_contract_bundle())
        except Exception:
            continue
        outputs.append(
            {
                "path": str(candidate.resolve()),
                "sha256": sha256_file(candidate),
                "row_count": inspection.row_count,
                "bar_interval": inspection.bar_interval,
                "symbol_values": inspection.symbol_values,
                "data_kind": inspection.data_kind,
            }
        )
    return tuple(outputs)


def _fetch_reconciliation_status(fetch_status: str, output_paths: tuple[str, ...], output_hashes: tuple[str, ...]) -> str:
    if fetch_status == "UPSTOX_FETCH_SUCCEEDED_REAL_CANDLES":
        if not output_paths:
            return "FETCH_SUCCESS_OUTPUT_MISSING"
        if not output_hashes or any(not h for h in output_hashes):
            return "FETCH_SUCCESS_OUTPUT_HASH_MISMATCH"
        return "FETCH_SUCCESS_RECONCILED"
    if fetch_status == "UPSTOX_FETCH_FAILED_NO_CANDLES":
        return "FETCH_FAILED_NO_CANDLES"
    if fetch_status == "UPSTOX_FETCH_FAILED_HTTP_ERROR":
        return "FETCH_FAILED_HTTP"
    if fetch_status:
        return "FETCH_PARTIAL"
    return "UNKNOWN"


def _error_classification(manifest: Mapping[str, Any]) -> str:
    status = str(manifest.get("fetch_status") or "")
    if "FAILED_HTTP" in status:
        return "FETCH_FAILED_HTTP"
    if "FAILED_NO_CANDLES" in status:
        return "FETCH_FAILED_NO_CANDLES"
    if "SUCCEEDED_REAL_CANDLES" in status:
        return "FETCH_SUCCESS_RECONCILED"
    return "UNKNOWN"


def _read_json_manifest_file(path: Path) -> dict[str, Any]:
    try:
        return _parse_manifest(path)
    except Exception:
        return {}


def _manifest_record(path: Path) -> FetchManifestRecord:
    payload = _read_json_manifest_file(path)
    outputs = _manifest_output_paths(path, payload)
    output_paths = tuple(str(item["path"]) for item in outputs)
    output_hashes = tuple(str(item["sha256"]) for item in outputs)
    requested_interval = _infer_manifest_requested_interval(payload, outputs)
    requested_instruments = _infer_manifest_requested_instruments(outputs)
    fetch_status = str(payload.get("fetch_status") or "MANIFEST_INVALID")
    return FetchManifestRecord(
        absolute_path=str(path.resolve()),
        logical_path=_canonical_logical_path(path),
        date=str(payload.get("date") or path.stem.replace(DEFAULT_FETCH_MANIFEST_PREFIX, "") or None),
        requested_instruments=requested_instruments,
        requested_interval=requested_interval,
        fetch_status=fetch_status,
        http_result=_fetch_reconciliation_status(fetch_status, output_paths, output_hashes),
        returned_rows=sum(int(item.get("row_count") or 0) for item in outputs) if outputs else None,
        output_paths=output_paths,
        output_hashes=output_hashes,
        retry_count=None,
        error_classification=_error_classification(payload),
        reconciliation_status=_fetch_reconciliation_status(fetch_status, output_paths, output_hashes),
        manifest_payload=payload,
    )


def _inspect_dataset_record(path: Path, bundle: dict[str, Any]) -> CorpusFileRecord:
    inspection = inspect_dataset(path, bundle=bundle)
    session_status = str(inspection.session_integrity.status if inspection.session_integrity else "NOT_APPLICABLE")
    if inspection.inspection_error:
        quality_status = "UNVERIFIABLE"
    elif inspection.row_count <= 0:
        quality_status = "PARTIAL"
    elif session_status == "UNREADABLE":
        quality_status = "UNVERIFIABLE"
    elif session_status == "FULL_SESSION":
        quality_status = "ACCEPTED"
    elif session_status in {"PARTIAL_SESSION", "GAPPED_SESSION", "DUPLICATE_SESSION", "OUT_OF_ORDER", "OFF_SESSION_CONTAMINATED"}:
        quality_status = "PARTIAL"
    elif session_status == "TIMEZONE_AMBIGUOUS":
        if inspection.data_kind.startswith("CANDLE") or str(inspection.bar_interval or "").lower() in {"1m", "1min", "1minute", "minute"}:
            quality_status = "UNVERIFIABLE"
        else:
            quality_status = "ACCEPTED"
    else:
        quality_status = "PARTIAL"
    return CorpusFileRecord(
        absolute_path=inspection.absolute_path,
        logical_path=_canonical_logical_path(path),
        source_root=_source_root_label(path),
        file_role="DATASET",
        data_role=_role_for_dataset(path, inspection),
        file_format=inspection.file_format,
        file_size_bytes=inspection.file_size_bytes,
        sha256=inspection.sha256,
        row_count=inspection.row_count,
        schema_columns=inspection.schema_columns,
        timestamp_field=inspection.timestamp_field,
        timestamp_timezone=inspection.timestamp_timezone,
        timestamp_min=inspection.timestamp_min,
        timestamp_max=inspection.timestamp_max,
        symbol_values=inspection.symbol_values,
        instrument_tokens=inspection.instrument_tokens,
        bar_interval=inspection.bar_interval,
        duplicate_rows_exact=inspection.duplicate_rows_exact,
        duplicate_rows_natural_key=inspection.duplicate_rows_natural_key,
        null_counts=inspection.null_counts,
        volume_sum=inspection.volume_sum,
        volume_nonzero_rows=inspection.volume_nonzero_rows,
        volume_truth_status=inspection.volume_truth_status,
        data_kind=inspection.data_kind,
        provenance=inspection.provenance,
        session_integrity=asdict(inspection.session_integrity) if inspection.session_integrity else None,
        inspection_error=inspection.inspection_error,
        quality_status=quality_status,
        accepted_for_snapshot=True,
        diff_status="UNCHANGED",
        diff_classification="NONE",
        exclusion_reason=inspection.exclusion_reason,
    )


def _cache_record(path: Path) -> CorpusFileRecord:
    return CorpusFileRecord(
        absolute_path=str(path.resolve()),
        logical_path=_canonical_logical_path(path),
        source_root=_source_root_label(path),
        file_role="CACHE_ARTIFACT",
        data_role="UNKNOWN",
        file_format=path.suffix.lower().lstrip(".") or "unknown",
        file_size_bytes=path.stat().st_size if path.exists() else 0,
        sha256=sha256_file(path) if path.exists() and path.is_file() else "",
        row_count=None,
        schema_columns=(),
        timestamp_field=None,
        timestamp_timezone=None,
        timestamp_min=None,
        timestamp_max=None,
        symbol_values=(),
        instrument_tokens=(),
        bar_interval=None,
        duplicate_rows_exact=None,
        duplicate_rows_natural_key=None,
        null_counts={},
        volume_sum=None,
        volume_nonzero_rows=None,
        volume_truth_status="UNVERIFIABLE",
        data_kind="UNKNOWN",
        provenance="UNKNOWN",
        session_integrity=None,
        inspection_error="cache_artifact",
        quality_status="UNVERIFIABLE",
        accepted_for_snapshot=False,
        diff_status="UNCHANGED",
        diff_classification="CACHE_ARTIFACT",
        exclusion_reason="cache_artifact",
        reconciliation_status="CACHE_ARTIFACT",
    )


def _parse_dataset_file(path: Path, bundle: dict[str, Any]) -> CorpusFileRecord:
    if _hidden_or_cache_file(path):
        return _cache_record(path)
    if path.suffix.lower() == ".jsonl" and path.exists() and path.stat().st_size == 0:
        return _cache_record(path)
    if _is_manifest_file(path):
        record = _manifest_record(path)
        payload = record.manifest_payload
        return CorpusFileRecord(
            absolute_path=record.absolute_path,
            logical_path=record.logical_path,
            source_root=_source_root_label(path),
            file_role="FETCH_MANIFEST" if path.name.startswith(DEFAULT_FETCH_MANIFEST_PREFIX) else "CAPTURE_MANIFEST",
            data_role="UNKNOWN",
            file_format="json",
            file_size_bytes=path.stat().st_size,
            sha256=sha256_file(path),
            row_count=int(payload.get("row_count") or payload.get("message_count") or 0) if payload else None,
            schema_columns=tuple({"name": k, "dtype": type(v).__name__} for k, v in sorted(payload.items())),
            timestamp_field="capture_timestamp" if "capture_timestamp" in payload else None,
            timestamp_timezone="naive" if payload.get("capture_timestamp") else None,
            timestamp_min=str(payload.get("capture_timestamp") or "") or None,
            timestamp_max=str(payload.get("capture_timestamp") or "") or None,
            symbol_values=(),
            instrument_tokens=(),
            bar_interval=str(payload.get("interval") or None),
            duplicate_rows_exact=None,
            duplicate_rows_natural_key=None,
            null_counts={},
            volume_sum=None,
            volume_nonzero_rows=None,
            volume_truth_status="NO_VOLUME_TRUTH",
            data_kind="MANIFEST",
            provenance=str(payload.get("provider") or payload.get("data_origin") or "UNKNOWN"),
            session_integrity=None,
            inspection_error="" if payload else "manifest_invalid",
            quality_status="ACCEPTED" if payload else "INVALID",
            accepted_for_snapshot=False,
            diff_status="METADATA_ONLY",
            diff_classification="MANIFEST",
            exclusion_reason="" if payload else "manifest_invalid",
            reconciliation_status=record.reconciliation_status,
        )
    try:
        return _inspect_dataset_record(path, bundle)
    except Exception as exc:
        return CorpusFileRecord(
            absolute_path=str(path.resolve()),
            logical_path=_canonical_logical_path(path),
            source_root=_source_root_label(path),
            file_role="DATASET",
            data_role="UNKNOWN",
            file_format=path.suffix.lower().lstrip(".") or "unknown",
            file_size_bytes=path.stat().st_size if path.exists() else 0,
            sha256=sha256_file(path) if path.exists() and path.is_file() else "",
            row_count=0,
            schema_columns=(),
            timestamp_field=None,
            timestamp_timezone=None,
            timestamp_min=None,
            timestamp_max=None,
            symbol_values=(),
            instrument_tokens=(),
            bar_interval=None,
            duplicate_rows_exact=0,
            duplicate_rows_natural_key=0,
            null_counts={},
            volume_sum=None,
            volume_nonzero_rows=None,
            volume_truth_status="INVALID_OR_UNVERIFIABLE",
            data_kind="INVALID_OR_UNVERIFIABLE",
            provenance="UNKNOWN",
            session_integrity=None,
            inspection_error=repr(exc),
            quality_status="UNVERIFIABLE",
            accepted_for_snapshot=True,
            diff_status="NEW",
            diff_classification="UNKNOWN",
            exclusion_reason=f"read_error:{exc!r}",
            reconciliation_status=None,
        )


def _dataset_snapshot_entries(records: Iterable[CorpusFileRecord]) -> list[dict[str, Any]]:
    entries = []
    for record in sorted(records, key=lambda item: item.logical_path):
        if not record.accepted_for_snapshot:
            continue
        entries.append(
            {
                "logical_path": record.logical_path,
                "sha256": record.sha256,
                "byte_size": record.file_size_bytes,
                "data_role": record.data_role,
            }
        )
    return entries


def _logical_file_map(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for item in manifest.get("dataset_records", []):
        canonical = _canonical_comparison_record(item)
        logical = f"{canonical['logical_source_role']}|{canonical['normalized_relative_path']}"
        if not logical:
            continue
        mapping[logical] = {**dict(item), **canonical}
    return mapping


def _compute_diff(
    current_records: list[CorpusFileRecord],
    previous_manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    previous_map = _logical_file_map(previous_manifest or {})
    current_map = {
        f"{record.data_role}|{record.logical_path}": record
        for record in current_records
        if record.accepted_for_snapshot
    }
    current_keys = set(current_map)
    previous_keys = set(previous_map)
    added = sorted(current_keys - previous_keys)
    removed = sorted(previous_keys - current_keys)
    shared = sorted(current_keys & previous_keys)
    changed = []
    unchanged = []
    for logical_path in shared:
        current = current_map[logical_path]
        previous = previous_map[logical_path]
        if str(current.sha256) == str(previous.get("content_sha256") or previous.get("sha256")) and int(current.file_size_bytes) == int(previous.get("byte_size") or previous.get("file_size_bytes") or 0):
            unchanged.append(logical_path)
        else:
            changed.append(
                {
                    "logical_path": logical_path,
                    "current_sha256": current.sha256,
                    "previous_sha256": str(previous.get("content_sha256") or previous.get("sha256") or ""),
                    "current_size": current.file_size_bytes,
                    "previous_size": int(previous.get("byte_size") or previous.get("file_size_bytes") or 0),
                    "classification": _classify_changed_file(previous, current),
                }
            )
    new_session_dates = sorted(
        {
            str(record.timestamp_min[:10])
            for record in current_records
            if record.accepted_for_snapshot and record.timestamp_min and record.file_role == "DATASET"
        }
    )
    previous_session_dates = sorted(
        {
            str(item.get("timestamp_min") or "")[:10]
            for item in previous_map.values()
            if item.get("timestamp_min")
        }
    )
    repaired_session_dates = sorted(set(new_session_dates) & set(previous_session_dates) & {str(item["logical_path"]).split("/")[-1][:8] for item in changed})
    return {
        "files_added": added,
        "files_removed": removed,
        "files_changed": changed,
        "files_unchanged": unchanged,
        "directories_added": sorted({Path(path).parent.as_posix() for path in added}),
        "new_session_dates": new_session_dates,
        "repaired_session_dates": repaired_session_dates,
        "new_option_contracts": _new_option_contracts(current_records, previous_manifest),
        "new_quote_coverage": _coverage_delta(current_records, previous_manifest, "OPTION_QUOTES"),
        "new_depth_coverage": _coverage_delta(current_records, previous_manifest, "OPTION_DEPTH"),
        "new_failed_fetches": _new_failed_fetches(current_records, previous_manifest),
        "resolved_previous_failures": _resolved_previous_failures(current_records, previous_manifest),
    }


def _classify_changed_file(previous: Mapping[str, Any], current: CorpusFileRecord) -> str:
    previous_quality = str(previous.get("quality_status") or previous.get("suitability_status") or "")
    current_quality = current.quality_status
    if previous_quality in {"INVALID", "INVALID_OR_UNVERIFIABLE", "UNVERIFIABLE"} and current_quality in {"ACCEPTED", "PARTIAL"}:
        return "REPAIRED_PREVIOUS_FAILURE"
    if str(previous.get("data_kind") or "") != current.data_kind and str(previous.get("file_format") or "") == current.file_format:
        return "FORMAT_CHANGED"
    if previous_quality == current_quality and str(previous.get("timestamp_min") or "")[:10] == str(current.timestamp_min or "")[:10]:
        return "REFETCHED_SAME_SESSION"
    if current_quality == "UNVERIFIABLE":
        return "CORRUPTED"
    return "CONTENT_CHANGED_UNEXPLAINED"


def _new_option_contracts(current_records: list[CorpusFileRecord], previous_manifest: Mapping[str, Any] | None) -> list[str]:
    current_contracts = sorted({record.logical_path for record in current_records if record.data_role.startswith("OPTION")})
    previous_contracts = sorted(
        {
            f"{_canonical_source_role(item)}|{_canonical_logical_path_text(item.get('relative_path') or item.get('absolute_path') or item.get('logical_path') or '')}"
            for item in (previous_manifest or {}).get("dataset_records", [])
            if "OPTION" in str(item.get("data_role") or "")
        }
    )
    return sorted(set(current_contracts) - set(previous_contracts))


def _coverage_delta(
    current_records: list[CorpusFileRecord],
    previous_manifest: Mapping[str, Any] | None,
    role: str,
) -> dict[str, Any]:
    current_paths = sorted(f"{record.data_role}|{record.logical_path}" for record in current_records if record.data_role == role)
    previous_paths = sorted(
        {
            f"{_canonical_source_role(item)}|{_canonical_logical_path_text(item.get('relative_path') or item.get('absolute_path') or item.get('logical_path') or '')}"
            for item in (previous_manifest or {}).get("dataset_records", [])
            if str(item.get("data_role") or "") == role
        }
    )
    return {
        "role": role,
        "current_count": len(current_paths),
        "previous_count": len(previous_paths),
        "new_paths": sorted(set(current_paths) - set(previous_paths)),
    }


def _new_failed_fetches(current_records: list[CorpusFileRecord], previous_manifest: Mapping[str, Any] | None) -> list[str]:
    return sorted(
        record.logical_path
        for record in current_records
        if record.file_role == "FETCH_MANIFEST" and record.reconciliation_status != "FETCH_SUCCESS_RECONCILED"
    )


def _resolved_previous_failures(current_records: list[CorpusFileRecord], previous_manifest: Mapping[str, Any] | None) -> list[str]:
    previous_failures = {
        f"{_canonical_source_role(item)}|{_canonical_logical_path_text(item.get('relative_path') or item.get('absolute_path') or item.get('logical_path') or '')}"
        for item in (previous_manifest or {}).get("dataset_records", [])
        if str(item.get("quality_status") or item.get("suitability_status") or "").startswith("INVALID")
    }
    current_ok = {
        f"{record.data_role}|{record.logical_path}"
        for record in current_records
        if record.quality_status in {"ACCEPTED", "PARTIAL"}
    }
    return sorted(previous_failures & current_ok)


def _family_key(record: CorpusFileRecord) -> tuple[Any, ...]:
    schema = tuple((item["name"], item["dtype"]) for item in record.schema_columns)
    symbol = record.symbol_values[0] if record.symbol_values else None
    return (
        record.data_role,
        _underlying_identity(record),
        _exchange_from_symbol(symbol),
        record.bar_interval,
        record.timestamp_timezone,
        tuple(sorted({d[:10] for d in _session_dates(record)})),
        "single_session",
        tuple(sorted({str(value) for value in _option_contract_coverage(record, "expiry")})),
        tuple(sorted({str(value) for value in _option_contract_coverage(record, "strike")})),
        tuple(sorted({str(value) for value in _option_contract_coverage(record, "option_type")})),
        schema,
    )


def _exchange_from_symbol(symbol: str | None) -> str | None:
    if not symbol:
        return None
    upper = symbol.upper()
    if upper.startswith("NSE_INDEX|"):
        return "NSE"
    if upper.startswith("BSE_INDEX|"):
        return "BSE"
    if upper.startswith("NIFTY") or upper.startswith("BANKNIFTY"):
        return "NSE"
    if upper.startswith("SENSEX"):
        return "BSE"
    return None


def _underlying_identity(record: CorpusFileRecord) -> str | None:
    if record.symbol_values:
        symbol = _normalize_underlying_symbol(record.symbol_values[0])
        return symbol
    return None


def _normalize_underlying_symbol(symbol: str | None) -> str | None:
    if not symbol:
        return None
    text = symbol.upper().replace("NSE_INDEX|", "").replace("BSE_INDEX|", "").strip()
    if "BANKNIFTY" in text or "NIFTY BANK" in text:
        return "BANKNIFTY"
    if "NIFTY 50" in text or text == "NIFTY" or text.startswith("NIFTY "):
        return "NIFTY"
    if "SENSEX" in text:
        return "SENSEX"
    if "|" in text:
        return text.split("|", 1)[-1].strip()
    return text.split()[0] if text.split() else None


def _session_dates(record: CorpusFileRecord) -> set[str]:
    dates: set[str] = set()
    for value in (record.timestamp_min, record.timestamp_max):
        if value:
            dates.add(str(value)[:10])
    return dates


def _option_contract_coverage(record: CorpusFileRecord, field: str) -> set[str]:
    values: set[str] = set()
    for column in record.schema_columns:
        if field in column["name"].lower():
            values.add(column["name"])
    return values


def _family_id(key: tuple[Any, ...]) -> str:
    canonical = json.dumps(key, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_families(records: list[CorpusFileRecord]) -> list[DatasetFamily]:
    grouped: dict[tuple[Any, ...], list[CorpusFileRecord]] = {}
    for record in records:
        if not record.accepted_for_snapshot or record.file_role == "CACHE_ARTIFACT":
            continue
        key = _family_key(record)
        grouped.setdefault(key, []).append(record)
    families: list[DatasetFamily] = []
    for key, items in sorted(grouped.items(), key=lambda kv: _family_id(kv[0])):
        component_hashes = tuple(sorted(record.sha256 for record in items))
        component_paths = tuple(sorted(record.logical_path for record in items))
        session_dates = tuple(sorted({date for record in items for date in _session_dates(record)}))
        schema = items[0].schema_columns
        family = DatasetFamily(
            family_id=_family_id(
                (
                    key[0],
                    key[1],
                    key[2],
                    key[3],
                    key[4],
                    key[5],
                    key[6],
                    key[7],
                    key[8],
                    key[9],
                    key[10],
                    component_hashes,
                )
            ),
            data_role=items[0].data_role,
            component_file_hashes=component_hashes,
            component_logical_paths=component_paths,
            underlying_identity=_underlying_identity(items[0]),
            symbol=items[0].symbol_values[0] if items[0].symbol_values else None,
            exchange=_exchange_from_symbol(items[0].symbol_values[0] if items[0].symbol_values else None),
            session_dates=session_dates,
            bar_interval=items[0].bar_interval,
            timezone=items[0].timestamp_timezone,
            expiry_coverage=tuple(sorted(_option_contract_coverage(items[0], "expiry"))),
            strike_coverage=tuple(sorted(_option_contract_coverage(items[0], "strike"))),
            option_type_coverage=tuple(sorted(_option_contract_coverage(items[0], "option_type"))),
            schema=schema,
            timestamp_range=(items[0].timestamp_min, items[0].timestamp_max),
            file_count=len(items),
        )
        families.append(family)
    return families


def _joinability(left: DatasetFamily, right: DatasetFamily) -> JoinabilityRecord:
    if left.family_id == right.family_id:
        return JoinabilityRecord(
            left_family_id=left.family_id,
            right_family_id=right.family_id,
            classification="EXACT_JOINABLE",
            reason="same family",
            join_direction="bidirectional",
            maximum_tolerance_seconds=0,
            tie_behavior="stable_sort_by_timestamp_then_path",
            missing_match_behavior="drop_non_matching_rows",
        )
    same_underlying = left.underlying_identity and left.underlying_identity == right.underlying_identity
    same_session = bool(set(left.session_dates) & set(right.session_dates))
    same_timezone = left.timezone == right.timezone
    if same_underlying and same_session and same_timezone:
        return JoinabilityRecord(
            left_family_id=left.family_id,
            right_family_id=right.family_id,
            classification="ASOF_JOINABLE_WITH_TOLERANCE",
            reason="same underlying, same session, compatible timezone",
            join_direction="left_to_right",
            maximum_tolerance_seconds=120,
            tie_behavior="nearest_previous_tie_break",
            missing_match_behavior="drop_missing_matches",
        )
    if same_underlying and same_timezone:
        return JoinabilityRecord(
            left_family_id=left.family_id,
            right_family_id=right.family_id,
            classification="SESSION_AGGREGATABLE",
            reason="same underlying but session windows differ",
            join_direction="session_aggregate",
            maximum_tolerance_seconds=None,
            tie_behavior=None,
            missing_match_behavior="session_bucket_only",
        )
    return JoinabilityRecord(
        left_family_id=left.family_id,
        right_family_id=right.family_id,
        classification="NOT_JOINABLE",
        reason="different underlying or timezone",
        join_direction="none",
        maximum_tolerance_seconds=None,
        tie_behavior=None,
        missing_match_behavior="reject_join",
    )


def _composite_for_strategy(strategy_id: str, families: list[DatasetFamily]) -> list[CompositeCorpus]:
    candle_families = [family for family in families if family.data_role == "UNDERLYING_CANDLES"]
    tick_families = [family for family in families if family.data_role == "UNDERLYING_TICKS"]
    option_ltp_families = [family for family in families if family.data_role == "OPTION_LTP"]
    option_quote_families = [family for family in families if family.data_role == "OPTION_QUOTES"]
    option_depth_families = [family for family in families if family.data_role == "OPTION_DEPTH"]
    composites: list[CompositeCorpus] = []

    if strategy_id == "opening_range_retest_v1":
        for candle in candle_families:
            matched_tick = next((family for family in tick_families if family.underlying_identity == candle.underlying_identity), None)
            matched_option = next((family for family in option_quote_families + option_depth_families + option_ltp_families if family.underlying_identity == candle.underlying_identity), None)
            components = [candle]
            if matched_tick:
                components.append(matched_tick)
            if matched_option:
                components.append(matched_option)
            composites.append(
                _composite_from_components(
                    strategy_id,
                    "SIGNAL_REPLAY",
                    components,
                    direct_fields=("completed_bar_history", "spot_ltp", "orb_high", "orb_low"),
                    derived_fields=("vwap", "premium_change", "spread", "depth"),
                    signal_suitability="PARTIAL" if not matched_option else "SUITABLE_WITH_PROVENANCE_LIMITATIONS",
                    execution_suitability="BLOCKED" if not matched_option or not option_depth_families else "PARTIAL",
                    blockers=("missing_option_quote_depth_history", "missing_exact_vwap_truth"),
                )
            )
            composites.append(
                _composite_from_components(
                    strategy_id,
                    "EXECUTION_REPLAY",
                    components,
                    direct_fields=("completed_bar_history", "spot_ltp", "orb_high", "orb_low"),
                    derived_fields=("vwap", "premium_change", "spread", "depth"),
                    signal_suitability="PARTIAL",
                    execution_suitability="BLOCKED" if not option_depth_families else "PARTIAL",
                    blockers=("missing_option_quote_depth_history",),
                )
            )
        return composites

    if strategy_id == "trend_pullback_v1":
        for candle in candle_families:
            matched_tick = next((family for family in tick_families if family.underlying_identity == candle.underlying_identity), None)
            components = [candle] + ([matched_tick] if matched_tick else [])
            composites.append(
                _composite_from_components(
                    strategy_id,
                    "SIGNAL_REPLAY",
                    components,
                    direct_fields=("completed_bar_history", "spot_ltp", "previous_completed_close"),
                    derived_fields=("vwap", "range_width_pct", "nearest_support", "nearest_resistance"),
                    signal_suitability="SUITABLE_WITH_PROVENANCE_LIMITATIONS",
                    execution_suitability="BLOCKED",
                    blockers=("missing_exact_vwap_truth",),
                )
            )
            composites.append(
                _composite_from_components(
                    strategy_id,
                    "EXECUTION_REPLAY",
                    components,
                    direct_fields=("completed_bar_history", "spot_ltp"),
                    derived_fields=("vwap", "range_width_pct", "nearest_support", "nearest_resistance"),
                    signal_suitability="SUITABLE_WITH_PROVENANCE_LIMITATIONS",
                    execution_suitability="BLOCKED",
                    blockers=("missing_execution_quotes_depth",),
                )
            )
        return composites

    if strategy_id == "compression_breakout_v1":
        for candle in candle_families:
            components = [candle]
            composites.append(
                _composite_from_components(
                    strategy_id,
                    "SIGNAL_REPLAY",
                    components,
                    direct_fields=("spot_ltp", "range_width_pct", "atr_short", "atr_long"),
                    derived_fields=("vwap", "nearest_support", "nearest_resistance"),
                    signal_suitability="SUITABLE_WITH_PROVENANCE_LIMITATIONS",
                    execution_suitability="BLOCKED",
                    blockers=("missing_exact_vwap_truth",),
                )
            )
            composites.append(
                _composite_from_components(
                    strategy_id,
                    "EXECUTION_REPLAY",
                    components,
                    direct_fields=("spot_ltp", "range_width_pct", "atr_short", "atr_long"),
                    derived_fields=("vwap", "nearest_support", "nearest_resistance"),
                    signal_suitability="SUITABLE_WITH_PROVENANCE_LIMITATIONS",
                    execution_suitability="BLOCKED",
                    blockers=("missing_execution_quotes_depth",),
                )
            )
        return composites

    if strategy_id == "vwap_reclaim_rejection_v1":
        for candle in candle_families:
            matched_tick = next((family for family in tick_families if family.underlying_identity == candle.underlying_identity), None)
            components = [candle] + ([matched_tick] if matched_tick else [])
            composites.append(
                _composite_from_components(
                    strategy_id,
                    "SIGNAL_REPLAY",
                    components,
                    direct_fields=("completed_bar_history", "spot_ltp", "previous_completed_close"),
                    derived_fields=("vwap", "vwap_slope", "volume_z"),
                    signal_suitability="SUITABLE_WITH_PROVENANCE_LIMITATIONS",
                    execution_suitability="BLOCKED",
                    blockers=("missing_exact_vwap_truth",),
                )
            )
            composites.append(
                _composite_from_components(
                    strategy_id,
                    "EXECUTION_REPLAY",
                    components,
                    direct_fields=("completed_bar_history", "spot_ltp"),
                    derived_fields=("vwap", "vwap_slope", "volume_z"),
                    signal_suitability="SUITABLE_WITH_PROVENANCE_LIMITATIONS",
                    execution_suitability="BLOCKED",
                    blockers=("missing_execution_quotes_depth",),
                )
            )
        return composites

    return composites


def _composite_from_components(
    strategy_id: str,
    replay_type: str,
    components: list[DatasetFamily],
    *,
    direct_fields: tuple[str, ...],
    derived_fields: tuple[str, ...],
    signal_suitability: str,
    execution_suitability: str,
    blockers: tuple[str, ...],
) -> CompositeCorpus:
    unique_components = sorted({family.family_id for family in components})
    canonical_descriptor = {
        "strategy_id": strategy_id,
        "replay_type": replay_type,
        "components": unique_components,
        "underlying_identity": components[0].underlying_identity if components else None,
        "session_range": tuple(sorted({date for family in components for date in family.session_dates})) if components else (),
        "timezone": components[0].timezone if components else None,
        "bar_interval": components[0].bar_interval if components else None,
        "join_policy": "same_underlying_same_session_with_bounded_asof",
    }
    composite_id = hashlib.sha256(
        json.dumps(canonical_descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    ).hexdigest()
    session_ranges = [family.session_dates for family in components if family.session_dates]
    flattened_sessions = sorted({date for dates in session_ranges for date in dates})
    return CompositeCorpus(
        composite_id=composite_id,
        replay_type=replay_type,
        strategy_id=strategy_id,
        component_family_ids=tuple(unique_components),
        component_file_hashes=tuple(sorted({file_hash for family in components for file_hash in family.component_file_hashes})),
        underlying_identity=components[0].underlying_identity if components else None,
        session_range=(flattened_sessions[0] if flattened_sessions else None, flattened_sessions[-1] if flattened_sessions else None),
        timezone=components[0].timezone if components else None,
        bar_interval=components[0].bar_interval if components else None,
        join_policy="same_underlying_same_session_with_bounded_asof",
        timestamp_tolerance_seconds=120 if replay_type == "SIGNAL_REPLAY" else 60,
        instrument_resolution_policy="existing_contract_only",
        direct_fields=direct_fields,
        derived_fields=derived_fields,
        provenance_limitations=("zero_volume_candle_vwap_proxy", "limited_option_quote_depth_history"),
        signal_suitability=signal_suitability,
        execution_suitability=execution_suitability,
        blockers=blockers,
    )


def _strategy_signal_execution_summary(
    strategy_id: str,
    families: list[DatasetFamily],
) -> dict[str, Any]:
    composites = _composite_for_strategy(strategy_id, families)
    signal_candidates = [item for item in composites if item.replay_type == "SIGNAL_REPLAY"]
    execution_candidates = [item for item in composites if item.replay_type == "EXECUTION_REPLAY"]
    signal_status = _reduce_signal_status(signal_candidates)
    execution_status = _reduce_execution_status(execution_candidates)
    blockers = sorted({blocker for item in composites for blocker in item.blockers})
    return {
        "strategy_id": strategy_id,
        "signal_suitability": signal_status,
        "execution_suitability": execution_status,
        "signal_replay_count": len(signal_candidates),
        "execution_replay_count": len(execution_candidates),
        "signal_composite_ids": [item.composite_id for item in signal_candidates],
        "execution_composite_ids": [item.composite_id for item in execution_candidates],
        "blockers": blockers,
    }


def _reduce_signal_status(composites: list[CompositeCorpus]) -> str:
    statuses = {item.signal_suitability for item in composites}
    if not statuses:
        return "BLOCKED"
    if statuses == {"SUITABLE"}:
        return "COMPOSITE_SIGNAL_DATA_READY"
    if "SUITABLE_WITH_PROVENANCE_LIMITATIONS" in statuses:
        return "COMPOSITE_SIGNAL_DATA_READY_WITH_PROVENANCE_LIMITATIONS"
    if "PARTIAL" in statuses:
        return "PARTIAL_COMPOSITE_SIGNAL_COVERAGE"
    return "NO_JOINABLE_COMPOSITE_CORPUS"


def _reduce_execution_status(composites: list[CompositeCorpus]) -> str:
    statuses = {item.execution_suitability for item in composites}
    if not statuses:
        return "BLOCKED"
    if statuses == {"SUITABLE"}:
        return "COMPOSITE_EXECUTION_DATA_READY"
    if "PARTIAL" in statuses:
        return "PARTIAL_EXECUTION_DATA_COVERAGE"
    return "EXECUTION_DATA_BLOCKED"


def _corpus_counts(records: list[CorpusFileRecord]) -> dict[str, Any]:
    return {
        "total_source_files": len(records),
        "valid_source_files": sum(1 for item in records if item.quality_status in {"ACCEPTED", "PARTIAL"}),
        "invalid_source_files": sum(1 for item in records if item.quality_status not in {"ACCEPTED", "PARTIAL"}),
        "unique_file_hashes": len({item.sha256 for item in records if item.sha256}),
        "historical_candle_files": sum(1 for item in records if item.data_role == "UNDERLYING_CANDLES"),
        "tick_files": sum(1 for item in records if item.data_role == "UNDERLYING_TICKS"),
        "quote_files": sum(1 for item in records if item.data_role == "OPTION_QUOTES"),
        "depth_files": sum(1 for item in records if item.data_role == "OPTION_DEPTH"),
        "manifest_files": sum(1 for item in records if item.file_role in {"FETCH_MANIFEST", "CAPTURE_MANIFEST"}),
    }


def _session_coverage(records: list[CorpusFileRecord], symbol_filter: str) -> dict[str, Any]:
    sessions: dict[str, str] = {}
    for item in records:
        if item.file_role != "DATASET" or not item.symbol_values:
            continue
        symbol = _normalize_underlying_symbol(item.symbol_values[0]) or ""
        if symbol_filter.upper() != symbol.upper():
            continue
        if item.timestamp_min:
            session_date = item.timestamp_min[:10]
            session_status = str((item.session_integrity or {}).get("status") or "UNREADABLE")
            current_status = sessions.get(session_date)
            status_order = {
                "FULL_SESSION": 0,
                "PARTIAL_SESSION": 1,
                "GAPPED_SESSION": 2,
                "OFF_SESSION_CONTAMINATED": 3,
                "DUPLICATE_SESSION": 4,
                "OUT_OF_ORDER": 5,
                "TIMEZONE_AMBIGUOUS": 6,
                "UNREADABLE": 7,
            }
            if current_status is None or status_order.get(session_status, 99) > status_order.get(current_status, 99):
                sessions[session_date] = session_status
    ordered_sessions = sorted(sessions)
    counts = {status: sum(1 for value in sessions.values() if value == status) for status in {
        "FULL_SESSION",
        "PARTIAL_SESSION",
        "GAPPED_SESSION",
        "DUPLICATE_SESSION",
        "OUT_OF_ORDER",
        "OFF_SESSION_CONTAMINATED",
        "TIMEZONE_AMBIGUOUS",
        "UNREADABLE",
    }}
    return {
        "session_count": len(ordered_sessions),
        "earliest_date": ordered_sessions[0] if ordered_sessions else None,
        "latest_date": ordered_sessions[-1] if ordered_sessions else None,
        "full_sessions": counts["FULL_SESSION"],
        "partial_sessions": counts["PARTIAL_SESSION"] + counts["OFF_SESSION_CONTAMINATED"],
        "gapped_sessions": counts["GAPPED_SESSION"],
        "duplicate_sessions": counts["DUPLICATE_SESSION"] + counts["OUT_OF_ORDER"],
        "unreadable_sessions": counts["UNREADABLE"] + counts["TIMEZONE_AMBIGUOUS"],
        "session_dates": ordered_sessions,
    }


def _option_history_coverage(records: list[CorpusFileRecord]) -> dict[str, Any]:
    option_roles = [item for item in records if item.data_role in {"OPTION_LTP", "OPTION_QUOTES", "OPTION_DEPTH"}]
    sessions = sorted({item.timestamp_min[:10] for item in option_roles if item.timestamp_min})
    quote_sessions = sorted({item.timestamp_min[:10] for item in option_roles if item.data_role == "OPTION_QUOTES" and item.timestamp_min})
    depth_sessions = sorted({item.timestamp_min[:10] for item in option_roles if item.data_role == "OPTION_DEPTH" and item.timestamp_min})
    return {
        "option_ltp_session_count": len(sessions),
        "option_quote_session_count": len(quote_sessions),
        "option_depth_session_count": len(depth_sessions),
        "two_year_option_coverage": "NOT_CURRENTLY_PROVEN" if not sessions else "PARTIAL",
    }


def build_upstox_corpus_inventory(
    *,
    roots: Iterable[Path] | None = None,
    bundle_path: Path | None = None,
    previous_manifest_path: Path | None = None,
    code_commit: str | None = None,
) -> dict[str, Any]:
    bundle = load_frozen_contract_bundle(bundle_path)
    requested_roots = [Path(root) for root in (roots or default_inventory_source_roots())]
    preflight_roots, active_roots = _audit_source_roots(requested_roots, finalize=False)
    if roots is not None:
        blocked = [record for record in preflight_roots if record.root_status in {"MISSING", "UNREADABLE", "INVALID"}]
        if blocked:
            raise FileNotFoundError(
                "requested_source_root_unavailable:"
                + ",".join(f"{item.requested_path}:{item.root_status}" for item in blocked)
            )
    source_files = discover_inventory_files(active_roots or requested_roots)
    records = [_parse_dataset_file(path, bundle) for path in source_files]
    source_root_authority, _ = _audit_source_roots(requested_roots, records, finalize=True)
    previous_manifest = _load_previous_manifest(previous_manifest_path)
    diff = _compute_diff(records, previous_manifest)
    families = _build_families(records)
    composites = [item for strategy in _strategy_ids(bundle) for item in _composite_for_strategy(strategy, families)]
    fetch_manifest_records = [asdict(_manifest_record(path)) for path in source_files if path.name.startswith(DEFAULT_FETCH_MANIFEST_PREFIX) or path.name.startswith(DEFAULT_CAPTURE_MANIFEST_PREFIX)]
    corpus_snapshot_entries = _dataset_snapshot_entries(records)
    corpus_snapshot_id = _snapshot_digest(corpus_snapshot_entries)
    data_snapshot_entries = _dataset_snapshot_entries([item for item in records if item.file_role == "DATASET"])
    data_snapshot_id = _snapshot_digest(data_snapshot_entries)
    inventory = {
        "schema_version": CORPUS_INVENTORY_SCHEMA_VERSION,
        "code_commit": code_commit or _current_git_commit(),
        "architecture_decision": bundle.get("architecture_decision"),
        "bundle_path": str((bundle_path or _default_bundle_path()).resolve()),
        "bundle_sha256": sha256_file(bundle_path or _default_bundle_path()),
        "previous_manifest_path": str(previous_manifest_path.resolve()) if previous_manifest_path else None,
        "previous_manifest_sha256": sha256_file(previous_manifest_path) if previous_manifest_path and previous_manifest_path.exists() else None,
        "requested_source_roots": [record.requested_path for record in source_root_authority],
        "source_roots": [record.resolved_path for record in source_root_authority],
        "source_root_authority": [asdict(record) for record in source_root_authority],
        "corpus_snapshot_id": corpus_snapshot_id,
        "data_snapshot_id": data_snapshot_id,
        "snapshot_policy": {
            "normalized_logical_path": "canonical_logical_path_family_key",
            "file_identity": "logical_path+sha256+byte_size+data_role",
            "cache_artifacts_excluded_from_snapshot": True,
            "manifest_files_included_in_inventory": True,
            "manifest_files_included_in_snapshot": False,
            "scan_time_excluded": True,
            "absolute_paths_non_authoritative": True,
        },
        "source_files": [asdict(item) for item in records],
        "fetch_manifest_records": fetch_manifest_records,
        "file_counts": _corpus_counts(records),
        "dataset_families": [asdict(item) for item in families],
        "composite_corpora": [asdict(item) for item in composites],
        "joinability_matrix": [asdict(_joinability(left, right)) for idx, left in enumerate(families) for right in families[idx + 1 :]],
        "coverage": {
            "nifty": _session_coverage(records, "NIFTY"),
            "banknifty": _session_coverage(records, "BANKNIFTY"),
            "other_underlyings": _other_underlying_coverage(records),
            "option_history": _option_history_coverage(records),
        },
        "diff": diff,
        "reconciliation": _fetch_reconciliation_summary(fetch_manifest_records),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_feed_used": False,
    }
    return inventory


def _fetch_reconciliation_summary(fetch_manifest_records: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for record in fetch_manifest_records:
        key = str(record.get("reconciliation_status") or "UNKNOWN")
        counts[key] = counts.get(key, 0) + 1
    return {
        "count": len(fetch_manifest_records),
        "by_status": counts,
        "records": fetch_manifest_records,
    }


def _compact_file_id(record: Mapping[str, Any]) -> str:
    seed = {
        "absolute_path": str(record.get("absolute_path") or ""),
        "logical_path": str(record.get("logical_path") or ""),
        "source_root": str(record.get("source_root") or ""),
        "sha256": str(record.get("sha256") or ""),
        "byte_size": int(record.get("file_size_bytes") or 0),
        "data_role": str(record.get("data_role") or ""),
        "file_role": str(record.get("file_role") or ""),
    }
    canonical = json.dumps(seed, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compact_file_record(record: Mapping[str, Any]) -> dict[str, Any]:
    session_integrity = record.get("session_integrity") or {}
    return {
        "logical_path": str(record.get("logical_path") or ""),
        "absolute_path": str(record.get("absolute_path") or ""),
        "source_root": str(record.get("source_root") or ""),
        "file_role": str(record.get("file_role") or ""),
        "data_role": str(record.get("data_role") or ""),
        "file_format": str(record.get("file_format") or ""),
        "sha256": str(record.get("sha256") or ""),
        "byte_size": int(record.get("file_size_bytes") or 0),
        "row_count": record.get("row_count"),
        "timestamp_min": record.get("timestamp_min"),
        "timestamp_max": record.get("timestamp_max"),
        "timestamp_field": record.get("timestamp_field"),
        "timestamp_timezone": record.get("timestamp_timezone"),
        "symbol_values": list(record.get("symbol_values") or []),
        "instrument_tokens": list(record.get("instrument_tokens") or []),
        "bar_interval": record.get("bar_interval"),
        "data_kind": record.get("data_kind"),
        "provenance": record.get("provenance"),
        "volume_truth_status": record.get("volume_truth_status"),
        "quality_status": record.get("quality_status"),
        "accepted_for_snapshot": bool(record.get("accepted_for_snapshot")),
        "exclusion_reason": record.get("exclusion_reason"),
        "reconciliation_status": record.get("reconciliation_status"),
        "session_status": str(session_integrity.get("status") or "UNREADABLE"),
    }


def _file_index(records: list[Mapping[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], str]]:
    compact: dict[str, dict[str, Any]] = {}
    lookup: dict[tuple[str, str], str] = {}
    for record in records:
        file_id = _compact_file_id(record)
        compact[file_id] = _compact_file_record(record)
        lookup[(str(record.get("logical_path") or ""), str(record.get("sha256") or ""))] = file_id
    return compact, lookup


def _compact_family_record(family: Mapping[str, Any], file_lookup: Mapping[tuple[str, str], str]) -> dict[str, Any]:
    component_file_ids: list[str] = []
    for logical_path, file_hash in zip(family.get("component_logical_paths", []), family.get("component_file_hashes", [])):
        file_id = file_lookup.get((str(logical_path), str(file_hash)))
        if file_id:
            component_file_ids.append(file_id)
    return {
        "family_id": str(family.get("family_id") or ""),
        "data_role": str(family.get("data_role") or ""),
        "component_file_ids": component_file_ids,
        "underlying_identity": family.get("underlying_identity"),
        "symbol": family.get("symbol"),
        "exchange": family.get("exchange"),
        "session_dates": list(family.get("session_dates") or []),
        "bar_interval": family.get("bar_interval"),
        "timezone": family.get("timezone"),
        "expiry_coverage": list(family.get("expiry_coverage") or []),
        "strike_coverage": list(family.get("strike_coverage") or []),
        "option_type_coverage": list(family.get("option_type_coverage") or []),
        "file_count": int(family.get("file_count") or 0),
    }


def _compact_joinability_summary(joinability_matrix: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    representatives: dict[str, list[dict[str, Any]]] = {}
    duplicate_pairs = 0
    for record in joinability_matrix:
        classification = str(record.get("classification") or "UNKNOWN")
        counts[classification] += 1
        if classification == "EXACT_JOINABLE":
            duplicate_pairs += 1
        bucket = representatives.setdefault(classification, [])
        if len(bucket) < 3:
            bucket.append(
                {
                    "left_family_id": str(record.get("left_family_id") or ""),
                    "right_family_id": str(record.get("right_family_id") or ""),
                    "reason": str(record.get("reason") or ""),
                    "join_direction": str(record.get("join_direction") or ""),
                    "maximum_tolerance_seconds": record.get("maximum_tolerance_seconds"),
                    "tie_behavior": record.get("tie_behavior"),
                    "missing_match_behavior": str(record.get("missing_match_behavior") or ""),
                }
            )
    return {
        "counts_by_class": dict(sorted(counts.items())),
        "representative_pairs": representatives,
        "duplicate_pairs": duplicate_pairs,
        "pair_count": sum(counts.values()),
    }


def _compact_duplicate_groups(records: list[Mapping[str, Any]], file_lookup: Mapping[tuple[str, str], str]) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        sha = str(record.get("sha256") or "")
        if not sha:
            continue
        groups.setdefault(sha, []).append(record)
    compact_groups: list[dict[str, Any]] = []
    for sha, items in sorted(groups.items(), key=lambda item: (len(item[1]), item[0]), reverse=True):
        if len(items) < 2:
            continue
        file_ids = []
        roles = []
        for item in items:
            file_id = file_lookup.get((str(item.get("logical_path") or ""), str(item.get("sha256") or "")))
            if file_id:
                file_ids.append(file_id)
            roles.append(str(item.get("data_role") or ""))
        compact_groups.append(
            {
                "sha256": sha,
                "file_ids": file_ids,
                "file_count": len(items),
                "roles": sorted(set(roles)),
            }
        )
    return compact_groups


def _compact_inventory_artifact(inventory: Mapping[str, Any]) -> dict[str, Any]:
    source_files = [dict(item) for item in inventory.get("source_files", [])]
    files, file_lookup = _file_index(source_files)
    hash_counts = Counter(str(item.get("sha256") or "") for item in source_files if item.get("sha256"))
    duplicate_group_count = sum(1 for count in hash_counts.values() if count > 1)
    duplicate_file_count = sum(count - 1 for count in hash_counts.values() if count > 1)
    families = {
        str(family.get("family_id") or ""): _compact_family_record(family, file_lookup)
        for family in inventory.get("dataset_families", [])
    }
    composites = {}
    for item in inventory.get("composite_corpora", []):
        composites[str(item.get("composite_id") or "")] = {
            "composite_id": str(item.get("composite_id") or ""),
            "strategy_id": str(item.get("strategy_id") or ""),
            "component_family_ids": list(item.get("component_family_ids") or []),
            "join_policy": str(item.get("join_policy") or ""),
            "timestamp_tolerance_seconds": item.get("timestamp_tolerance_seconds"),
            "instrument_resolution_policy": str(item.get("instrument_resolution_policy") or ""),
            "direct_fields": list(item.get("direct_fields") or []),
            "derived_fields": list(item.get("derived_fields") or []),
            "provenance_limitations": list(item.get("provenance_limitations") or []),
            "signal_suitability": str(item.get("signal_suitability") or ""),
            "execution_suitability": str(item.get("execution_suitability") or ""),
            "blockers": list(item.get("blockers") or []),
            "underlying_identity": item.get("underlying_identity"),
            "session_range": list(item.get("session_range") or []),
            "timezone": item.get("timezone"),
            "bar_interval": item.get("bar_interval"),
        }
    return {
        "schema_version": inventory.get("schema_version"),
        "code_commit": inventory.get("code_commit"),
        "architecture_decision": inventory.get("architecture_decision"),
        "bundle_path": inventory.get("bundle_path"),
        "bundle_sha256": inventory.get("bundle_sha256"),
        "previous_manifest_path": inventory.get("previous_manifest_path"),
        "previous_manifest_sha256": inventory.get("previous_manifest_sha256"),
        "requested_source_roots": list(inventory.get("requested_source_roots") or []),
        "source_roots": list(inventory.get("source_roots") or []),
        "source_root_authority": list(inventory.get("source_root_authority") or []),
        "corpus_snapshot_id": inventory.get("corpus_snapshot_id"),
        "data_snapshot_id": inventory.get("data_snapshot_id"),
        "snapshot_policy": dict(inventory.get("snapshot_policy") or {}),
        "file_counts": dict(inventory.get("file_counts") or {}),
        "coverage": dict(inventory.get("coverage") or {}),
        "diff": dict(inventory.get("diff") or {}),
        "reconciliation": dict(inventory.get("reconciliation") or {}),
        "files": files,
        "families": families,
        "composites": composites,
        "joinability_summary": _compact_joinability_summary(inventory.get("joinability_matrix") or []),
        "duplicate_content_counts": {
            "duplicate_content_group_count": duplicate_group_count,
            "duplicate_file_count": duplicate_file_count,
        },
        "duplicate_content_summary": {
            "duplicate_content_group_count": duplicate_group_count,
            "duplicate_file_count": duplicate_file_count,
            "duplicate_groups": _compact_duplicate_groups(source_files, file_lookup),
        },
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_feed_used": False,
    }


def _compact_manifest_artifact(manifest: Mapping[str, Any]) -> dict[str, Any]:
    inventory_summary = dict(manifest.get("inventory_summary") or {})
    strategy_summary = [
        {
            "strategy_id": str(item.get("strategy_id") or ""),
            "signal_suitability": str(item.get("signal_suitability") or ""),
            "execution_suitability": str(item.get("execution_suitability") or ""),
            "blockers": list(item.get("blockers") or []),
            "composite_id": item.get("composite_id"),
            "join_class": item.get("join_class"),
        }
        for item in manifest.get("strategy_summary", [])
    ]
    composite_corpora = [
        {
            "composite_id": str(item.get("composite_id") or ""),
            "strategy_id": str(item.get("strategy_id") or ""),
            "component_family_ids": list(item.get("component_family_ids") or []),
            "join_policy": str(item.get("join_policy") or ""),
            "timestamp_tolerance_seconds": item.get("timestamp_tolerance_seconds"),
            "instrument_resolution_policy": str(item.get("instrument_resolution_policy") or ""),
            "direct_fields": list(item.get("direct_fields") or []),
            "derived_fields": list(item.get("derived_fields") or []),
            "provenance_limitations": list(item.get("provenance_limitations") or []),
            "signal_suitability": str(item.get("signal_suitability") or ""),
            "execution_suitability": str(item.get("execution_suitability") or ""),
            "blockers": list(item.get("blockers") or []),
            "underlying_identity": item.get("underlying_identity"),
            "session_range": list(item.get("session_range") or []),
            "timezone": item.get("timezone"),
            "bar_interval": item.get("bar_interval"),
        }
        for item in manifest.get("composite_corpora", [])
    ]
    return {
        "schema_version": manifest.get("schema_version"),
        "code_commit": manifest.get("code_commit"),
        "architecture_decision": manifest.get("architecture_decision"),
        "bundle_path": manifest.get("bundle_path"),
        "bundle_sha256": manifest.get("bundle_sha256"),
        "previous_manifest_path": manifest.get("previous_manifest_path"),
        "corpus_snapshot_id": manifest.get("corpus_snapshot_id"),
        "data_snapshot_id": manifest.get("data_snapshot_id"),
        "inventory_sha256": manifest.get("inventory_sha256"),
        "inventory_path": manifest.get("inventory_path"),
        "requested_source_roots": list(manifest.get("requested_source_roots") or []),
        "source_roots": list(manifest.get("source_roots") or []),
        "source_root_authority": list(manifest.get("source_root_authority") or []),
        "inventory_summary": inventory_summary,
        "coverage": dict(manifest.get("coverage") or {}),
        "joinability_summary": dict(manifest.get("joinability_summary") or {}),
        "composite_generation_policy": {
            "policy_version": "compact_v1",
            "counts_by_strategy": {item["strategy_id"]: item["signal_suitability"] for item in strategy_summary},
            "representative_accepted_composites": [item["composite_id"] for item in composite_corpora if item["signal_suitability"] in {"COMPOSITE_SIGNAL_DATA_READY", "COMPOSITE_SIGNAL_DATA_READY_WITH_PROVENANCE_LIMITATIONS"}],
            "representative_rejected_composites": [item["composite_id"] for item in composite_corpora if item["signal_suitability"] not in {"COMPOSITE_SIGNAL_DATA_READY", "COMPOSITE_SIGNAL_DATA_READY_WITH_PROVENANCE_LIMITATIONS"}],
            "canonical_composite_id_hash_root": "sha256(strategy_id|component_family_ids|join_policy|signal_suitability|execution_suitability)",
            "duplicate_removal_counts": {
                "duplicate_content_group_count": int(inventory_summary.get("duplicate_content_group_count") or 0),
                "duplicate_file_count": int(inventory_summary.get("duplicate_file_count") or 0),
            },
        },
        "composite_corpora": composite_corpora,
        "strategy_summary": strategy_summary,
        "signal_verdict": manifest.get("signal_verdict"),
        "execution_verdict": manifest.get("execution_verdict"),
        "corpus_status": manifest.get("corpus_status"),
        "corpus_blockers": list(manifest.get("corpus_blockers") or []),
        "incremental_diff": dict(manifest.get("incremental_diff") or {}),
        "fetch_reconciliation": dict(manifest.get("fetch_reconciliation") or {}),
        "provenance_policy": dict(manifest.get("provenance_policy") or {}),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_feed_used": False,
    }


def _write_compact_json_and_sidecar(payload: Mapping[str, Any], *, output_path: Path) -> tuple[Path, Path]:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str) + "\n"
    output_path.write_text(serialized, encoding="utf-8")
    sha = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    sidecar_path = output_path.with_suffix(output_path.suffix + ".sha256")
    sidecar_path.write_text(f"{sha}  {output_path.name}\n", encoding="utf-8")
    return output_path, sidecar_path


def _other_underlying_coverage(records: list[CorpusFileRecord]) -> dict[str, Any]:
    symbols = sorted(
        {
            _normalize_underlying_symbol(item.symbol_values[0]) or item.symbol_values[0]
            for item in records
            if item.file_role == "DATASET"
            and item.symbol_values
            and (_normalize_underlying_symbol(item.symbol_values[0]) or "") not in {"NIFTY", "BANKNIFTY"}
        }
    )
    sessions: dict[tuple[str, str], str] = {}
    for item in records:
        if item.file_role != "DATASET" or not item.symbol_values or not item.timestamp_min:
            continue
        symbol = _normalize_underlying_symbol(item.symbol_values[0]) or item.symbol_values[0]
        if symbol.upper() in {"NIFTY", "BANKNIFTY"}:
            continue
        session_date = item.timestamp_min[:10]
        session_status = str((item.session_integrity or {}).get("status") or "UNREADABLE")
        key = (symbol, session_date)
        current_status = sessions.get(key)
        status_order = {
            "FULL_SESSION": 0,
            "PARTIAL_SESSION": 1,
            "GAPPED_SESSION": 2,
            "OFF_SESSION_CONTAMINATED": 3,
            "DUPLICATE_SESSION": 4,
            "OUT_OF_ORDER": 5,
            "TIMEZONE_AMBIGUOUS": 6,
            "UNREADABLE": 7,
        }
        if current_status is None or status_order.get(session_status, 99) > status_order.get(current_status, 99):
            sessions[key] = session_status
    ordered_sessions = sorted({date for _, date in sessions})
    counts = {status: sum(1 for value in sessions.values() if value == status) for status in {
        "FULL_SESSION",
        "PARTIAL_SESSION",
        "GAPPED_SESSION",
        "DUPLICATE_SESSION",
        "OUT_OF_ORDER",
        "OFF_SESSION_CONTAMINATED",
        "TIMEZONE_AMBIGUOUS",
        "UNREADABLE",
    }}
    return {
        "symbols": symbols,
        "session_count": len(ordered_sessions),
        "full_sessions": counts["FULL_SESSION"],
        "partial_sessions": counts["PARTIAL_SESSION"] + counts["OFF_SESSION_CONTAMINATED"],
        "gapped_sessions": counts["GAPPED_SESSION"],
        "duplicate_sessions": counts["DUPLICATE_SESSION"] + counts["OUT_OF_ORDER"],
        "unreadable_sessions": counts["UNREADABLE"] + counts["TIMEZONE_AMBIGUOUS"],
        "session_dates": ordered_sessions,
    }


def _strategy_ids(bundle: Mapping[str, Any]) -> list[str]:
    return [
        str(entry.get("runtime_strategy_id") or entry.get("canonical_strategy_id") or "UNKNOWN")
        for entry in bundle.get("strategies", [])
    ]


def _load_previous_manifest(previous_manifest_path: Path | None) -> dict[str, Any]:
    if not previous_manifest_path:
        return {}
    path = Path(previous_manifest_path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_four_strategy_dataset_manifest_v2(
    *,
    roots: Iterable[Path] | None = None,
    bundle_path: Path | None = None,
    previous_manifest_path: Path | None = None,
    code_commit: str | None = None,
    inventory: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    inventory = dict(inventory or build_upstox_corpus_inventory(
        roots=roots,
        bundle_path=bundle_path,
        previous_manifest_path=previous_manifest_path,
        code_commit=code_commit,
    ))
    bundle = load_frozen_contract_bundle(bundle_path)
    families = [DatasetFamily(**item) for item in inventory.get("dataset_families", [])]
    strategy_summaries = [_strategy_signal_execution_summary(strategy, families) for strategy in _strategy_ids(bundle)]
    signal_statuses = {item["signal_suitability"] for item in strategy_summaries}
    execution_statuses = {item["execution_suitability"] for item in strategy_summaries}
    if signal_statuses == {"COMPOSITE_SIGNAL_DATA_READY"}:
        signal_verdict = "COMPOSITE_SIGNAL_DATA_READY"
    elif "COMPOSITE_SIGNAL_DATA_READY_WITH_PROVENANCE_LIMITATIONS" in signal_statuses:
        signal_verdict = "COMPOSITE_SIGNAL_DATA_READY_WITH_PROVENANCE_LIMITATIONS"
    elif "PARTIAL_COMPOSITE_SIGNAL_COVERAGE" in signal_statuses:
        signal_verdict = "PARTIAL_COMPOSITE_SIGNAL_COVERAGE"
    else:
        signal_verdict = "NO_JOINABLE_COMPOSITE_CORPUS"
    if execution_statuses == {"COMPOSITE_EXECUTION_DATA_READY"}:
        execution_verdict = "COMPOSITE_EXECUTION_DATA_READY"
    elif "PARTIAL_EXECUTION_DATA_COVERAGE" in execution_statuses:
        execution_verdict = "PARTIAL_EXECUTION_DATA_COVERAGE"
    else:
        execution_verdict = "EXECUTION_DATA_BLOCKED"
    return {
        "schema_version": CORPUS_INVENTORY_SCHEMA_VERSION,
        "code_commit": inventory.get("code_commit") or code_commit or _current_git_commit(),
        "architecture_decision": bundle.get("architecture_decision"),
        "bundle_path": inventory.get("bundle_path") or str((bundle_path or _default_bundle_path()).resolve()),
        "bundle_sha256": inventory.get("bundle_sha256") or sha256_file(bundle_path or _default_bundle_path()),
        "previous_manifest_path": str(previous_manifest_path.resolve()) if previous_manifest_path else None,
        "corpus_snapshot_id": inventory.get("corpus_snapshot_id"),
        "data_snapshot_id": inventory.get("data_snapshot_id"),
        "inventory_sha256": None,
        "inventory_path": str((Path("docs") / "agent_reviews" / "upstox_corpus_inventory_v2.json").resolve()),
        "requested_source_roots": inventory.get("requested_source_roots", []),
        "source_roots": inventory.get("source_roots", []),
        "source_root_authority": inventory.get("source_root_authority", []),
        "inventory_summary": {
            "total_source_files": inventory["file_counts"]["total_source_files"],
            "valid_source_files": inventory["file_counts"]["valid_source_files"],
            "invalid_source_files": inventory["file_counts"]["invalid_source_files"],
            "unique_file_hashes": inventory["file_counts"]["unique_file_hashes"],
            "dataset_family_count": len(inventory.get("dataset_families", [])),
            "composite_corpus_count": len(inventory.get("composite_corpora", [])),
            "joinable_composite_count": sum(1 for item in inventory.get("composite_corpora", []) if item.get("signal_suitability") in {"SUITABLE_WITH_PROVENANCE_LIMITATIONS", "COMPOSITE_SIGNAL_DATA_READY"}),
        },
        "coverage": inventory.get("coverage", {}),
        "joinability_matrix": inventory.get("joinability_matrix", []),
        "dataset_families": inventory.get("dataset_families", []),
        "composite_corpora": inventory.get("composite_corpora", []),
        "strategy_summary": strategy_summaries,
        "signal_verdict": signal_verdict,
        "execution_verdict": execution_verdict,
        "corpus_status": "SUITABLE" if signal_verdict == "COMPOSITE_SIGNAL_DATA_READY" and execution_verdict == "COMPOSITE_EXECUTION_DATA_READY" else "PARTIAL",
        "corpus_blockers": sorted({blocker for item in strategy_summaries for blocker in item["blockers"]}),
        "incremental_diff": inventory.get("diff", {}),
        "fetch_reconciliation": inventory.get("reconciliation", {}),
        "provenance_policy": {
            "corpus_snapshot": "sha256(logical_path|sha256|byte_size|data_role)",
            "inventory_serialization": "canonical_json_sorted_keys",
            "scan_time": "not_part_of_identity",
        },
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_feed_used": False,
    }


def write_inventory_and_sidecar(inventory: dict[str, Any], *, output_path: Path) -> tuple[Path, Path]:
    return _write_compact_json_and_sidecar(_compact_inventory_artifact(inventory), output_path=output_path)


def write_v2_manifest_and_sidecar(manifest: dict[str, Any], *, output_path: Path) -> tuple[Path, Path]:
    return _write_compact_json_and_sidecar(_compact_manifest_artifact(manifest), output_path=output_path)
