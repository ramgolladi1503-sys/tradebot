#!/usr/bin/env python3
"""Create a read-only, hash-bound inventory for legacy T-1 source inputs.

This legacy format cannot establish a frozen strategy prerequisite. In
particular, a point-in-time snapshot LTP is not a prior-session close, loose
CSV timestamp matching is not an exact futures bar contract, and an unbound
200-row slice is not a calendar-verified SMA series. Values therefore remain
null and blocked. Runtime readiness requires a separately pinned heritage
graph manifest verified by ``core.market_heritage_verifier``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

MAX_INVENTORY_SOURCE_BYTES = 512 * 1024 * 1024


def _sha256_file(path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    if not path.is_file():
        raise FileNotFoundError(f"Source dataset not found: {path}")
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


def compute_manifest(
    *,
    source_snapshot_path: Path,
    source_session_date: str,
    target_session_date: str,
    historical_daily_dataset_path: Optional[Path] = None,
    futures_dataset_path: Optional[Path] = None,
    contract_key: Optional[str] = None,
    target_expiry: Optional[str] = None,
) -> dict[str, Any]:
    """Hash the supplied legacy files without promoting market values."""
    if not source_snapshot_path.is_file():
        raise FileNotFoundError(f"Source snapshot not found: {source_snapshot_path}")
    source_date = date.fromisoformat(source_session_date)
    target_date = date.fromisoformat(target_session_date)
    if source_date >= target_date:
        raise ValueError("SOURCE_SESSION_MUST_PRECEDE_TARGET_SESSION")
    snapshot_sha256 = _sha256_file(source_snapshot_path)
    if snapshot_sha256 is None:
        raise ValueError("SOURCE_SNAPSHOT_HASH_MISSING")
    created_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    futures_sha256 = _sha256_file(futures_dataset_path)
    historical_sha256 = _sha256_file(historical_daily_dataset_path)

    report: dict[str, Any] = {
        "schema_version": 2,
        "artifact_type": "LEGACY_T1_SOURCE_INVENTORY",
        "source_snapshot": str(source_snapshot_path),
        "source_snapshot_sha256": snapshot_sha256,
        "source_session_date": source_session_date,
        "target_session_date": target_session_date,
        "created_at_utc": created_at_utc,
        "opening_drive_prev_contract_key": None,
        "opening_drive_prev_contract_key_status": "BLOCKED_SOURCE_AUTHORITY",
        "opening_drive_prev_close_1529": None,
        "opening_drive_prev_close_1529_status": "BLOCKED_SOURCE_AUTHORITY",
        "opening_drive_target_expiry": None,
        "overnight_prev_daily_close": None,
        "overnight_prev_daily_close_status": "BLOCKED_SOURCE_AUTHORITY",
        "overnight_prev_sma200": None,
        "sma200_status": "BLOCKED_SOURCE_AUTHORITY",
        "sma200_calculation_window_days": 0,
        "futures_dataset_path": str(futures_dataset_path) if futures_dataset_path else None,
        "futures_dataset_sha256": futures_sha256,
        "futures_row_count": None,
        "historical_dataset_path": str(historical_daily_dataset_path) if historical_daily_dataset_path else None,
        "historical_dataset_sha256": historical_sha256,
        "calendar_status": "BLOCKED_SOURCE_AUTHORITY",
        "manifest_status": "BLOCKED_SOURCE_AUTHORITY",
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    # Values supplied by callers are recorded only as untrusted hints. They
    # are not prerequisite values and cannot make the report verified.
    report["untrusted_contract_key_hint"] = contract_key
    report["untrusted_target_expiry_hint"] = target_expiry
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    report["payload_sha256"] = hashlib.sha256(canonical).hexdigest()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory legacy T-1 source files without promoting values")
    parser.add_argument("--source-dataset", type=Path, required=True, help="Path to a legacy market snapshot")
    parser.add_argument("--source-session-date", type=str, required=True)
    parser.add_argument("--target-session-date", type=str, required=True)
    parser.add_argument("--historical-daily-dataset", type=Path, default=None)
    parser.add_argument("--futures-dataset", type=Path, default=None)
    parser.add_argument("--contract-key", type=str, default=None)
    parser.add_argument("--target-expiry", type=str, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    doc = compute_manifest(
        source_snapshot_path=args.source_dataset,
        source_session_date=args.source_session_date,
        target_session_date=args.target_session_date,
        historical_daily_dataset_path=args.historical_daily_dataset,
        futures_dataset_path=args.futures_dataset,
        contract_key=args.contract_key,
        target_expiry=args.target_expiry,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Generated blocked legacy T-1 source inventory at {args.output}")
    print(json.dumps(doc, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
