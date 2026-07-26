from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .root_scan import (
    InvalidRootSpecError,
    RootPermissionError,
    RootSpec,
    UnsupportedFilesystemEntryError,
    classify_source_candidate,
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
    candidate_ids: list[str] = []
    resolved_seen: set[Path] = set()
    for spec in sorted(root_specs, key=lambda item: item.root_id):
        if spec.path.is_symlink() or not spec.path.is_dir():
            raise InvalidRootSpecError(f"oracle_root_missing:{spec.root_id}")
        root = spec.path.resolve(strict=True)
        if root in resolved_seen:
            raise InvalidRootSpecError("oracle_duplicate_resolved_root")
        resolved_seen.add(root)
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames.sort()
            filenames.sort()
            for name in list(dirnames):
                candidate = Path(directory) / name
                if candidate.is_symlink():
                    raise UnsupportedFilesystemEntryError(
                        f"oracle_symlink_directory:{spec.root_id}:{candidate.relative_to(root)}"
                    )
            total_directories += len(dirnames)
            for name in filenames:
                candidate = Path(directory) / name
                relative = candidate.relative_to(root).as_posix()
                if candidate.is_symlink():
                    raise UnsupportedFilesystemEntryError(
                        f"oracle_symlink_file:{spec.root_id}:{relative}"
                    )
                try:
                    if not candidate.is_file():
                        raise UnsupportedFilesystemEntryError(
                            f"oracle_non_regular:{spec.root_id}:{relative}"
                        )
                except PermissionError as exc:
                    raise RootPermissionError(
                        f"oracle_unreadable:{spec.root_id}:{relative}"
                    ) from exc
                total_files += 1
                if classify_source_candidate(relative) is not None:
                    candidate_ids.append(f"{spec.root_id}:{relative}")
    manifest = hashlib.sha256()
    for candidate_id in sorted(candidate_ids):
        manifest.update(f"{candidate_id}\n".encode("utf-8"))
    return {
        "declared_root_count": len(root_specs),
        "total_file_count": total_files,
        "total_directory_count": total_directories,
        "source_candidate_count": len(candidate_ids),
        "candidate_id_manifest_sha256": manifest.hexdigest(),
        "scan_complete": True,
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
        "root_candidate_count": root_primary.get("source_candidate_count")
        == root_oracle.get("source_candidate_count"),
        "root_candidate_manifest": candidate_manifest.hexdigest()
        == root_oracle.get("candidate_id_manifest_sha256"),
        "scan_complete": root_primary.get("scan_complete") is True
        and root_oracle.get("scan_complete") is True,
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
