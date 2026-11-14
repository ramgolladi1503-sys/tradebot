from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .root_scan import (
    EXCLUDED_DIRECTORY_NAMES,
    InvalidRootSpecError,
    OverlappingResolvedRootError,
    RootPermissionError,
    RootSpec,
    UnsupportedFilesystemEntryError,
    classify_source_candidate,
    is_outcome_or_pnl_path,
    _iter_entries,
)
from .trace_audit import (
    OutcomeBearingFieldError,
    TraceFormatError,
    TraceHashMismatchError,
    TraceMissingError,
)

_DENIED = (
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
_EXCLUDED_DIRECTORY_NAME_SET = frozenset(EXCLUDED_DIRECTORY_NAMES)
_NOT_OPENED_DIGEST = "NOT_OPENED_BY_POLICY"


def _key_is_denied(key: str) -> bool:
    normalized = key.casefold().replace("-", "_").replace(" ", "_")
    return any(token in normalized for token in _DENIED)


def _flatten_keys(value: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for raw_key in sorted(value, key=str):
            key = str(raw_key)
            path = f"{prefix}.{key}" if prefix else key
            if _key_is_denied(key):
                raise OutcomeBearingFieldError(f"oracle_denied_key:{path}")
            paths.append(path)
            paths.extend(_flatten_keys(value[raw_key], path))
    elif isinstance(value, list):
        for nested in value:
            paths.extend(_flatten_keys(nested, prefix))
    return paths


def oracle_trace_facts(
    path: Path,
    *,
    expected_sha256: str | None = None,
    max_line_bytes: int = 2 * 1024 * 1024,
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise TraceMissingError(f"oracle_trace_missing:{path}")
    raw_digest = hashlib.sha256()
    semantic_digest = hashlib.sha256()
    key_digest = hashlib.sha256()
    record_count = 0
    blank_line_count = 0
    timestamps: list[datetime] = []
    with path.open("rb") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            raw_digest.update(raw_line)
            if len(raw_line) > max_line_bytes:
                raise TraceFormatError(f"oracle_line_too_large:line={line_no}")
            stripped = raw_line.strip()
            if not stripped:
                blank_line_count += 1
                continue
            try:
                payload = json.loads(stripped.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise TraceFormatError(f"oracle_invalid_jsonl:line={line_no}") from exc
            if not isinstance(payload, dict):
                raise TraceFormatError(f"oracle_record_not_object:line={line_no}")
            for required in ("timestamp", "module", "stage"):
                if required not in payload:
                    raise TraceFormatError(
                        f"oracle_required_key_missing:{required}:line={line_no}"
                    )
            text = str(payload["timestamp"])
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError as exc:
                raise TraceFormatError(f"oracle_invalid_timestamp:line={line_no}") from exc
            if parsed.tzinfo is None:
                raise TraceFormatError(f"oracle_naive_timestamp:line={line_no}")
            timestamps.append(parsed.astimezone(timezone.utc))
            canonical = (
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                )
                + "\n"
            ).encode("utf-8")
            semantic_digest.update(canonical)
            for key_path in sorted(set(_flatten_keys(payload))):
                key_digest.update(f"{key_path}\n".encode("utf-8"))
            record_count += 1
    digest = raw_digest.hexdigest()
    if expected_sha256 is not None and digest != expected_sha256.lower():
        raise TraceHashMismatchError(
            f"oracle_trace_hash_mismatch:expected={expected_sha256.lower()}:actual={digest}"
        )
    return {
        "trace_sha256": digest,
        "trace_size_bytes": path.stat().st_size,
        "record_count": record_count,
        "blank_line_count": blank_line_count,
        "first_timestamp_utc": min(timestamps).isoformat() if timestamps else None,
        "last_timestamp_utc": max(timestamps).isoformat() if timestamps else None,
        "key_path_manifest_sha256": key_digest.hexdigest(),
        "semantic_record_stream_sha256": semantic_digest.hexdigest(),
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def oracle_root_facts(
    root_specs: Sequence[RootSpec],
    *,
    expected_root_count: int = 27,
) -> dict[str, Any]:
    if len(root_specs) != expected_root_count:
        raise InvalidRootSpecError(
            f"oracle_root_count_mismatch:expected={expected_root_count}:actual={len(root_specs)}"
        )
    root_ids = [spec.root_id for spec in root_specs]
    if len(root_ids) != len(set(root_ids)):
        raise InvalidRootSpecError("oracle_duplicate_root_id")
    total_files = 0
    total_directories = 0
    excluded_directory_count = 0
    denied_candidate_count = 0
    all_file_manifest = hashlib.sha256()
    excluded_directory_manifest = hashlib.sha256()
    candidate_rows: list[tuple[str, str | None, str, bool]] = []
    resolved_roots: list[tuple[RootSpec, Path]] = []
    for spec in sorted(root_specs, key=lambda item: item.root_id):
        if spec.path.is_symlink() or not spec.path.is_dir():
            raise InvalidRootSpecError(f"oracle_root_absent:{spec.root_id}")
        root = spec.path.resolve(strict=True)
        for existing_spec, existing_root in resolved_roots:
            if root == existing_root:
                raise InvalidRootSpecError("oracle_duplicate_resolved_root")
            if root.is_relative_to(existing_root) or existing_root.is_relative_to(root):
                raise OverlappingResolvedRootError(
                    f"oracle_overlapping_roots:{existing_spec.root_id}:{spec.root_id}"
                )
        resolved_roots.append((spec, root))

    for spec, root in sorted(resolved_roots, key=lambda item: item[0].root_id):
        for relative, entry, excluded_directory in _iter_entries(spec.root_id, root):
            try:
                stat_result = entry.stat(follow_symlinks=False)
            except PermissionError as exc:
                raise RootPermissionError(
                    f"oracle_entry_stat_failed:{spec.root_id}:{relative}"
                ) from exc
            if stat.S_ISDIR(stat_result.st_mode):
                total_directories += 1
                if excluded_directory:
                    excluded_directory_count += 1
                    excluded_directory_manifest.update(
                        f"{spec.root_id}\0{relative}\n".encode("utf-8")
                    )
                continue
            if not stat.S_ISREG(stat_result.st_mode):
                raise UnsupportedFilesystemEntryError(
                    f"oracle_non_regular:{spec.root_id}:{relative}"
                )
            candidate = root / Path(relative)
            size = stat_result.st_size
            all_file_manifest.update(
                f"{spec.root_id}\0{relative}\0{size}\n".encode("utf-8")
            )
            total_files += 1
            candidate_class = classify_source_candidate(relative)
            if candidate_class is None:
                continue
            denied = is_outcome_or_pnl_path(relative)
            digest: str | None = None
            if denied:
                denied_candidate_count += 1
            else:
                file_digest = hashlib.sha256()
                try:
                    with candidate.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            file_digest.update(chunk)
                except PermissionError as exc:
                    raise RootPermissionError(
                        f"oracle_candidate_unreadable:{spec.root_id}:{relative}"
                    ) from exc
                digest = file_digest.hexdigest()
            candidate_rows.append(
                (f"{spec.root_id}:{relative}", digest, candidate_class, denied)
            )

    candidate_manifest = hashlib.sha256()
    candidate_id_manifest = hashlib.sha256()
    for candidate_id, digest, candidate_class, denied in sorted(candidate_rows):
        candidate_id_manifest.update(f"{candidate_id}\n".encode("utf-8"))
        manifest_digest = digest if digest is not None else _NOT_OPENED_DIGEST
        candidate_manifest.update(
            (
                f"{candidate_id}\0{manifest_digest}\0{candidate_class}\0"
                f"{int(denied)}\n"
            ).encode("utf-8")
        )
    return {
        "declared_root_count": len(root_specs),
        "total_file_count": total_files,
        "total_directory_count": total_directories,
        "excluded_directory_names": list(EXCLUDED_DIRECTORY_NAMES),
        "excluded_directory_count": excluded_directory_count,
        "excluded_directory_path_manifest_sha256": excluded_directory_manifest.hexdigest(),
        "source_candidate_count": len(candidate_rows),
        "denied_outcome_or_pnl_candidate_count": denied_candidate_count,
        "all_file_identity_manifest_sha256": all_file_manifest.hexdigest(),
        "candidate_id_manifest_sha256": candidate_id_manifest.hexdigest(),
        "candidate_identity_manifest_sha256": candidate_manifest.hexdigest(),
        "scan_complete": True,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def reconcile_primary_oracle(
    trace_primary: dict[str, Any],
    root_primary: dict[str, Any],
    trace_oracle: dict[str, Any],
    root_oracle: dict[str, Any],
) -> dict[str, Any]:
    candidate_manifest = hashlib.sha256()
    for row in root_primary["source_candidates"]:
        candidate_manifest.update(f"{row['candidate_id']}\n".encode("utf-8"))
    checks = {
        "trace_sha256": trace_primary.get("trace_sha256") == trace_oracle.get("trace_sha256"),
        "trace_size_bytes": trace_primary.get("trace_size_bytes")
        == trace_oracle.get("trace_size_bytes"),
        "trace_record_count": trace_primary.get("record_count")
        == trace_oracle.get("record_count"),
        "trace_blank_line_count": trace_primary.get("blank_line_count")
        == trace_oracle.get("blank_line_count"),
        "trace_first_timestamp": trace_primary.get("first_timestamp_utc")
        == trace_oracle.get("first_timestamp_utc"),
        "trace_last_timestamp": trace_primary.get("last_timestamp_utc")
        == trace_oracle.get("last_timestamp_utc"),
        "trace_semantic_stream": trace_primary.get("semantic_record_stream_sha256")
        == trace_oracle.get("semantic_record_stream_sha256"),
        "trace_key_manifest": trace_primary.get("key_path_manifest_sha256")
        == trace_oracle.get("key_path_manifest_sha256"),
        "root_count": root_primary.get("declared_root_count")
        == root_oracle.get("declared_root_count"),
        "root_file_count": root_primary.get("total_file_count")
        == root_oracle.get("total_file_count"),
        "root_directory_count": root_primary.get("total_directory_count")
        == root_oracle.get("total_directory_count"),
        "root_excluded_directory_names": root_primary.get("excluded_directory_names")
        == root_oracle.get("excluded_directory_names"),
        "root_excluded_directory_count": root_primary.get("excluded_directory_count")
        == root_oracle.get("excluded_directory_count"),
        "root_excluded_directory_manifest": root_primary.get(
            "excluded_directory_path_manifest_sha256"
        )
        == root_oracle.get("excluded_directory_path_manifest_sha256"),
        "root_candidate_count": root_primary.get("source_candidate_count")
        == root_oracle.get("source_candidate_count"),
        "root_denied_candidate_count": root_primary.get(
            "denied_outcome_or_pnl_candidate_count"
        )
        == root_oracle.get("denied_outcome_or_pnl_candidate_count"),
        "root_candidate_id_manifest": candidate_manifest.hexdigest()
        == root_oracle.get("candidate_id_manifest_sha256"),
        "root_all_file_manifest": root_primary.get("all_file_identity_manifest_sha256")
        == root_oracle.get("all_file_identity_manifest_sha256"),
        "root_candidate_content_manifest": root_primary.get(
            "candidate_identity_manifest_sha256"
        )
        == root_oracle.get("candidate_identity_manifest_sha256"),
        "scan_complete": root_primary.get("scan_complete") is True
        and root_oracle.get("scan_complete") is True,
        "outcome_boundary": all(
            root_primary.get(key) is False and root_oracle.get(key) is False
            for key in ("outcomes_read", "pnl_read", "holdout_outcomes_read")
        ),
        "safety": all(
            trace_primary.get(key) == trace_oracle.get(key)
            and root_primary.get(key) == root_oracle.get(key)
            for key in (
                "research_only",
                "read_only",
                "is_order_action",
                "broker_api_called",
                "allowed_for_live_execution",
            )
        ),
    }
    return {
        "status": "AGREEMENT" if all(checks.values()) else "DISAGREEMENT",
        "checks": checks,
    }
