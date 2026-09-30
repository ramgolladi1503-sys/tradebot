#!/usr/bin/env python3
"""Independent verifier for the fail-closed legacy T-1 inventory.

This verifier authenticates file references and the inventory payload only. It
does not certify market values. Runtime prerequisites require the separate
content-addressed graph verifier and pinned manifest path/hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

MAX_INVENTORY_SOURCE_BYTES = 512 * 1024 * 1024


def _sha256_file(path: Path) -> str:
    before = path.stat()
    if before.st_size > MAX_INVENTORY_SOURCE_BYTES:
        raise ValueError("SOURCE_FILE_SIZE_BOUND_EXCEEDED")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError("SOURCE_CHANGED_DURING_HASH")
    return digest.hexdigest()


def _verify_optional_source(doc: dict[str, Any], path_key: str, sha_key: str) -> bool:
    source = doc.get(path_key)
    digest = doc.get(sha_key)
    if source is None:
        if digest is not None:
            raise ValueError(f"{sha_key} must be null when {path_key} is absent")
        return False
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"Underlying source missing: {source_path}")
    if _sha256_file(source_path) != digest:
        raise ValueError(f"{sha_key} mismatch")
    return True


def verify_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    if doc.get("schema_version") != 2 or doc.get("artifact_type") != "LEGACY_T1_SOURCE_INVENTORY":
        raise ValueError("Unsupported artifact schema or type")

    snapshot_path = Path(doc["source_snapshot"])
    if not snapshot_path.is_file():
        raise FileNotFoundError(f"Underlying snapshot missing: {snapshot_path}")
    snapshot_sha = _sha256_file(snapshot_path)
    if snapshot_sha != doc.get("source_snapshot_sha256"):
        raise ValueError("Source snapshot SHA-256 mismatch")

    futures_present = _verify_optional_source(doc, "futures_dataset_path", "futures_dataset_sha256")
    history_present = _verify_optional_source(doc, "historical_dataset_path", "historical_dataset_sha256")
    blocked_fields = {
        "opening_drive_prev_contract_key": "opening_drive_prev_contract_key_status",
        "opening_drive_prev_close_1529": "opening_drive_prev_close_1529_status",
        "overnight_prev_daily_close": "overnight_prev_daily_close_status",
        "overnight_prev_sma200": "sma200_status",
    }
    for value_key, status_key in blocked_fields.items():
        if doc.get(value_key) is not None:
            raise ValueError(f"{value_key} cannot be promoted by a legacy inventory")
        if doc.get(status_key) != "BLOCKED_SOURCE_AUTHORITY":
            raise ValueError(f"{status_key} must remain BLOCKED_SOURCE_AUTHORITY")
    if doc.get("opening_drive_target_expiry") is not None:
        raise ValueError("opening_drive_target_expiry cannot be promoted by a legacy inventory")
    if doc.get("sma200_calculation_window_days") != 0 or doc.get("futures_row_count") is not None:
        raise ValueError("legacy inventory cannot claim source row or calculation coverage")
    if doc.get("calendar_status") != "BLOCKED_SOURCE_AUTHORITY" or doc.get("manifest_status") != "BLOCKED_SOURCE_AUTHORITY":
        raise ValueError("calendar and manifest authority must remain blocked")
    if (doc.get("read_only") is not True or doc.get("append") is not False
            or doc.get("is_order_action") is not False
            or doc.get("broker_api_called") is not False
            or doc.get("allowed_for_live_execution") is not False):
        raise ValueError("Authority boundary invalid")

    payload_copy = dict(doc)
    stored_sha = payload_copy.pop("payload_sha256", None)
    canonical = json.dumps(payload_copy, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    recalculated = hashlib.sha256(canonical).hexdigest()
    if stored_sha != recalculated:
        raise ValueError("Inventory payload SHA-256 mismatch")

    return {
        "manifest_path": str(manifest_path),
        "source_snapshot_sha_verified": True,
        "futures_source_hash_verified": futures_present,
        "historical_source_hash_verified": history_present,
        "data_authority": "BLOCKED_SOURCE_AUTHORITY",
        "payload_sha_verified": True,
        "independent_oracle_verdict": "PASS_BLOCKED_INVENTORY_ONLY",
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a blocked legacy T-1 source inventory")
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_manifest(args.manifest), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
