"""Governed audit-chain forensic recovery and rollover module.

Performs forensic preservation of broken/truncated audit chains:
1. Cryptographically hashes the original audit log.
2. Preserves byte-for-byte immutable archive copy.
3. Records forensic manifest with failure root cause and unlinked hashes.
4. Generates a fresh AUDIT_CHAIN_BOOTSTRAP event starting from GENESIS that
   explicitly binds predecessor log hash, last event hash, tool SHA, and reason.
5. Verifies new chain integrity before completing.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.audit_log import (
    AUDIT_LOG,
    GENESIS,
    _canonical_json,
    _compute_hash,
    verify_chain,
)


def perform_audit_chain_rollover(
    *,
    audit_log_path: Path = AUDIT_LOG,
    reason: str = "governed_audit_chain_forensic_rollover",
    tool_sha: str = "",
    certified_release_sha: str = "",
    new_run_id: str = "",
) -> dict[str, Any]:
    """Execute a forensically bound audit chain rollover."""
    audit_log = Path(audit_log_path).resolve()
    if not audit_log.is_file():
        raise FileNotFoundError(f"Audit log not found at {audit_log}")

    raw_bytes = audit_log.read_bytes()
    orig_sha = hashlib.sha256(raw_bytes).hexdigest()
    lines = raw_bytes.decode("utf-8", errors="replace").splitlines()

    ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = audit_log.parent / f"forensic_audit_log_archive_{ts_str}.jsonl"
    manifest_path = audit_log.parent / f"forensic_manifest_{ts_str}.json"

    archive_path.write_bytes(raw_bytes)
    arch_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if arch_sha != orig_sha:
        raise RuntimeError("CORRUPTED_ARCHIVE_COPY_HASH_MISMATCH")

    first_event = {}
    last_event = {}
    if lines:
        try:
            first_event = json.loads(lines[0])
        except Exception:
            pass
        try:
            last_event = json.loads(lines[-1])
        except Exception:
            pass

    manifest = {
        "action": "FORENSIC_AUDIT_CHAIN_ROLLOVER",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "original_path": str(audit_log),
        "archive_path": str(archive_path),
        "archive_sha256": orig_sha,
        "total_records": len(lines),
        "first_record_ts_ist": first_event.get("ts_ist"),
        "last_record_ts_ist": last_event.get("ts_ist"),
        "first_record_prev_hash": first_event.get("prev_hash"),
        "last_record_event_hash": last_event.get("event_hash"),
        "first_failure_reason": (
            "prev_hash_mismatch: Record 0 prev_hash != GENESIS"
            if first_event.get("prev_hash") != GENESIS
            else "chain_tamper_or_truncation"
        ),
        "tool_sha": str(tool_sha),
        "certified_release_sha": str(certified_release_sha),
        "reason": str(reason),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    run_id = str(new_run_id or f"forensic_recovery_{ts_str}").strip()
    now_epoch = time.time()
    bootstrap_event: dict[str, Any] = {
        "event": "AUDIT_CHAIN_BOOTSTRAP",
        "run_id": run_id,
        "boot_epoch": now_epoch,
        "source": "core.audit_chain_recovery.perform_audit_chain_rollover",
        "desk_id": first_event.get("desk_id", "DEFAULT"),
        "is_order_action": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "rollover_forensic_evidence": {
            "predecessor_archive_path": str(archive_path),
            "predecessor_archive_sha256": orig_sha,
            "predecessor_last_event_hash": last_event.get("event_hash"),
            "forensic_manifest_path": str(manifest_path),
            "rollover_reason": str(reason),
            "certified_release_sha": str(certified_release_sha),
            "tool_sha": str(tool_sha),
        },
        "ts_epoch": now_epoch,
        "ts_ist": datetime.now().astimezone().isoformat(),
        "prev_hash": GENESIS,
    }
    bootstrap_event["event_hash"] = _compute_hash(bootstrap_event)

    tmp_path = audit_log.with_name(f".{audit_log.name}.tmp.{ts_str}")
    tmp_path.write_text(json.dumps(bootstrap_event, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(audit_log)

    ok, status, count = verify_chain(audit_log, expected_run_id=run_id)
    if not ok:
        raise RuntimeError(f"AUDIT_CHAIN_ROLLOVER_VERIFY_FAILED:{status}")

    return {
        "success": True,
        "manifest_path": str(manifest_path),
        "archive_path": str(archive_path),
        "archive_sha256": orig_sha,
        "new_genesis_hash": bootstrap_event["event_hash"],
        "count": count,
    }
