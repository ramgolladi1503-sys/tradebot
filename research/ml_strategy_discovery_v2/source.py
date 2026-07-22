from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifacts import sha256_file
from .contracts import DEVELOPMENT, canonical_hash


class SourceCertificationError(ValueError):
    """Raised when a source manifest or record fails certification."""


def verify_manifest_sidecar(manifest_path: str | Path) -> str:
    manifest = Path(manifest_path)
    sidecar = Path(f"{manifest}.sha256")
    if not manifest.is_file():
        raise SourceCertificationError(f"source manifest is missing: {manifest}")
    if not sidecar.is_file():
        raise SourceCertificationError(f"source manifest sidecar is missing: {sidecar}")
    fields = sidecar.read_text(encoding="utf-8").strip().split()
    if len(fields) != 2:
        raise SourceCertificationError(
            "source manifest sidecar must contain digest and filename"
        )
    declared_digest, declared_filename = fields
    if declared_filename != manifest.name:
        raise SourceCertificationError(
            f"source manifest sidecar filename mismatch: {declared_filename} != {manifest.name}"
        )
    actual = sha256_file(manifest)
    if declared_digest.lower() != actual:
        raise SourceCertificationError(
            f"source manifest sidecar digest mismatch: {declared_digest} != {actual}"
        )
    return actual


def load_and_verify_manifest(
    manifest_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = Path(manifest_path)
    manifest_hash = verify_manifest_sidecar(manifest)
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceCertificationError("source manifest JSON is malformed") from exc
    if not isinstance(payload, dict) or payload.get("source_manifest_version") not in {
        "v2",
        "v2.1",
    }:
        raise SourceCertificationError("source manifest version v2 or v2.1 is required")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise SourceCertificationError("source manifest records are required")
    if payload.get("record_count") is not None and int(payload["record_count"]) != len(records):
        raise SourceCertificationError("source manifest record_count mismatch")
    expected = sorted(
        records,
        key=lambda item: (
            str(item.get("session_date") or ""),
            str(item.get("logical_path") or ""),
            str(item.get("actual_sha256") or ""),
        ),
    )
    if records != expected:
        raise SourceCertificationError(
            "source manifest records are not deterministically ordered"
        )
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    seen_symbol_sessions: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict):
            raise SourceCertificationError("source manifest record must be an object")
        logical_path = str(record.get("logical_path") or "")
        logical = Path(logical_path)
        if not logical_path or logical.is_absolute() or ".." in logical.parts:
            raise SourceCertificationError(
                f"unsafe source logical path: {logical_path!r}"
            )
        if logical.parts[:2] != ("runtime", "upstox_candidate_replay"):
            raise SourceCertificationError(
                f"source path outside authority root: {logical_path}"
            )
        record_id = str(record.get("source_record_id") or "")
        symbol = str(record.get("symbol") or "")
        session_date = str(record.get("session_date") or "")
        digest = str(record.get("actual_sha256") or "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise SourceCertificationError(f"invalid source digest: {logical_path}")
        if not record_id or not symbol or not session_date:
            raise SourceCertificationError(
                f"incomplete source record metadata: {logical_path}"
            )
        if (
            record_id in seen_ids
            or logical_path in seen_paths
            or (symbol, session_date) in seen_symbol_sessions
        ):
            raise SourceCertificationError(f"duplicate source record: {record_id}")
        seen_ids.add(record_id)
        seen_paths.add(logical_path)
        seen_symbol_sessions.add((symbol, session_date))
        if record.get("byte_size") is None:
            raise SourceCertificationError(
                f"source byte_size is required: {logical_path}"
            )
    policies = payload.get("special_session_policies", [])
    if not isinstance(policies, list):
        raise SourceCertificationError("special_session_policies must be a list")
    for policy in policies:
        if not isinstance(policy, dict) or policy.get("policy") != "EXCLUDE_SPECIAL_SESSION_WITH_RECORDED_REASON":
            raise SourceCertificationError("unsupported special-session policy")
        required = {"session_date", "symbol", "expected_rows", "actual_rows", "reason"}
        if required.difference(policy):
            raise SourceCertificationError("special-session policy is incomplete")
        if int(policy["actual_rows"]) == int(policy["expected_rows"]):
            raise SourceCertificationError(
                "special-session exclusion cannot describe a complete session"
            )
    identity = {
        "manifest_sha256": manifest_hash,
        "record_count": len(records),
        "record_set_hash": canonical_hash(records),
        "special_session_policy_count": len(policies),
        "special_session_policy_hash": canonical_hash(policies),
        "coverage_start": min(str(record["session_date"]) for record in records),
        "coverage_end": max(str(record["session_date"]) for record in records),
    }
    return payload, identity


def selected_instrument_records(
    payload: dict[str, Any], instrument: str
) -> list[dict[str, Any]]:
    normalized = instrument.upper().strip()
    records = [
        record
        for record in payload["records"]
        if str(record.get("symbol") or "").upper().strip()
        in {normalized, f"NSE_INDEX|{normalized}"}
    ]
    if not records:
        raise SourceCertificationError(f"manifest contains no records for {instrument}")
    return records


def development_manifest_payload(
    payload: dict[str, Any],
    *,
    instrument: str,
    registry: Any,
) -> dict[str, Any]:
    selected = [
        record
        for record in selected_instrument_records(payload, instrument)
        if registry.classify(str(record["session_date"])) == DEVELOPMENT
    ]
    if not selected:
        raise SourceCertificationError("manifest contains no DEVELOPMENT_V1 records")
    selected = sorted(
        selected,
        key=lambda item: (
            str(item["session_date"]),
            str(item["logical_path"]),
            str(item["actual_sha256"]),
        ),
    )
    return {
        "source_manifest_version": "v2",
        "selection_contract": "ML_STRATEGY_DISCOVERY_V2_DEVELOPMENT_ONLY",
        "parent_manifest_record_set_hash": canonical_hash(payload["records"]),
        "record_count": len(selected),
        "records": selected,
        "special_session_policies": [
            policy
            for policy in payload.get("special_session_policies", [])
            if registry.classify(str(policy["session_date"])) == DEVELOPMENT
        ],
    }


def resolve_source_file(project_root: str | Path, logical_path: str) -> Path:
    root = Path(project_root).expanduser().resolve()
    allowed = (root / "runtime/upstox_candidate_replay").resolve()
    logical = Path(str(logical_path))
    if (
        logical.is_absolute()
        or ".." in logical.parts
        or logical.parts[:2] != ("runtime", "upstox_candidate_replay")
    ):
        raise SourceCertificationError(f"unsafe source logical path: {logical_path!r}")
    current = root
    for part in logical.parts:
        current = current / part
        if current.is_symlink():
            raise SourceCertificationError(
                f"source path contains a symlink: {logical_path}"
            )
    resolved = (root / logical).resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as exc:
        raise SourceCertificationError(
            f"source path escapes authority root: {logical_path}"
        ) from exc
    if not resolved.is_file():
        raise SourceCertificationError(f"source file is missing: {logical_path}")
    return resolved


def verify_record_file(
    project_root: str | Path, record: dict[str, Any]
) -> dict[str, Any]:
    logical_path = str(record.get("logical_path") or "")
    resolved = resolve_source_file(project_root, logical_path)
    actual_sha = sha256_file(resolved)
    expected_sha = str(record.get("actual_sha256") or "")
    if actual_sha != expected_sha:
        raise SourceCertificationError(
            f"source SHA-256 mismatch path={logical_path} expected={expected_sha} actual={actual_sha}"
        )
    actual_size = resolved.stat().st_size
    if int(record.get("byte_size", -1)) != actual_size:
        raise SourceCertificationError(f"source byte-size mismatch path={logical_path}")
    return {
        "logical_path": logical_path,
        "actual_sha256": actual_sha,
        "byte_size": actual_size,
        "source_record_id": str(record.get("source_record_id") or ""),
        "session_date": str(record.get("session_date") or ""),
        "symbol": str(record.get("symbol") or ""),
    }


def verify_selected_record_files(
    project_root: str | Path, records: list[dict[str, Any]]
) -> dict[str, Any]:
    verified = [verify_record_file(project_root, record) for record in records]
    return {
        "record_count": len(verified),
        "record_set_hash": canonical_hash(verified),
        "records": verified,
    }
