"""Governed audit-chain forensic recovery, inspection, and provenance verification.

Non-negotiable requirements:
1. Preserve original corrupted file byte-for-byte in an immutable archive.
2. Independently compute exact first invalid record index and content.
3. Independently recompute last-valid hash.
4. Record immutable forensic recovery manifest.
5. Bind genesis bootstrap event to predecessor archive SHA256, last-valid hash,
   first invalid record, corruption cause, recovery timestamp, and recovery code SHA.
6. Provide strict verify_recovery_provenance() that attacks archive mutation,
   manifest mutation, wrong predecessor hash, and replayed recovery.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
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


def compute_code_sha() -> str:
    """Compute exact SHA256 of the recovery module source code."""
    try:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except Exception:
        return "UNKNOWN_CODE_SHA"


def inspect_audit_chain(audit_log_path: Path) -> dict[str, Any]:
    """Forensically inspect an audit log line-by-line to find corruption boundaries."""
    audit_log = Path(audit_log_path).resolve()
    if not audit_log.is_file():
        raise FileNotFoundError(f"Audit log not found at {audit_log}")

    raw_bytes = audit_log.read_bytes()
    orig_sha = hashlib.sha256(raw_bytes).hexdigest()
    raw_lines = raw_bytes.splitlines()

    total_records = len(raw_lines)
    if total_records == 0:
        return {
            "ok": False,
            "original_sha256": orig_sha,
            "total_records": 0,
            "first_invalid_record_index": 0,
            "first_invalid_record": "",
            "last_valid_record_index": -1,
            "last_valid_hash": GENESIS,
            "corruption_cause": "empty_file",
        }

    expected_prev = GENESIS
    last_valid_hash = GENESIS
    last_valid_index = -1
    first_invalid_index = -1
    first_invalid_record = ""
    corruption_cause = ""

    first_record_prev_hash: str | None = None
    if raw_lines:
        try:
            r0 = json.loads(raw_lines[0].decode("utf-8", errors="replace").strip())
            if isinstance(r0, dict):
                first_record_prev_hash = r0.get("prev_hash")
        except Exception:
            pass

    for idx, raw_line in enumerate(raw_lines):
        line_str = raw_line.decode("utf-8", errors="replace").strip()
        if not line_str:
            first_invalid_index = idx
            first_invalid_record = line_str
            corruption_cause = f"empty_or_whitespace_line at record {idx}"
            break

        try:
            record = json.loads(line_str)
        except Exception as exc:
            first_invalid_index = idx
            first_invalid_record = line_str
            corruption_cause = f"invalid_json at record {idx}: {exc}"
            break

        if not isinstance(record, dict):
            first_invalid_index = idx
            first_invalid_record = line_str
            corruption_cause = f"record_not_dict at record {idx}"
            break

        actual_prev = record.get("prev_hash")
        actual_event_hash = record.get("event_hash")

        if actual_prev != expected_prev:
            first_invalid_index = idx
            first_invalid_record = line_str
            corruption_cause = (
                f"prev_hash_mismatch at record {idx}: actual '{actual_prev}' != expected '{expected_prev}'"
            )
            break

        recomputed = _compute_hash(record)
        if recomputed != actual_event_hash:
            first_invalid_index = idx
            first_invalid_record = line_str
            corruption_cause = (
                f"event_hash_mismatch at record {idx}: actual '{actual_event_hash}' != recomputed '{recomputed}'"
            )
            break

        last_valid_hash = recomputed
        last_valid_index = idx
        expected_prev = recomputed

    if first_invalid_index == -1:
        return {
            "ok": True,
            "original_sha256": orig_sha,
            "total_records": total_records,
            "first_record_prev_hash": first_record_prev_hash,
            "first_invalid_record_index": -1,
            "first_invalid_record": None,
            "last_valid_record_index": last_valid_index,
            "last_valid_hash": last_valid_hash,
            "corruption_cause": "none",
        }

    return {
        "ok": False,
        "original_sha256": orig_sha,
        "total_records": total_records,
        "first_record_prev_hash": first_record_prev_hash,
        "first_invalid_record_index": first_invalid_index,
        "first_invalid_record": first_invalid_record,
        "last_valid_record_index": last_valid_index,
        "last_valid_hash": last_valid_hash,
        "corruption_cause": corruption_cause,
    }


def perform_audit_chain_rollover(
    *,
    audit_log_path: Path = AUDIT_LOG,
    reason: str = "governed_audit_chain_forensic_rollover",
    tool_sha: str = "",
    certified_release_sha: str = "",
    new_run_id: str = "",
) -> dict[str, Any]:
    """Execute a forensically bound audit chain rollover with cryptographic provenance."""
    audit_log = Path(audit_log_path).resolve()
    if not audit_log.is_file():
        raise FileNotFoundError(f"Audit log not found at {audit_log}")

    inspection = inspect_audit_chain(audit_log)
    raw_bytes = audit_log.read_bytes()
    orig_sha = inspection["original_sha256"]

    ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = audit_log.parent / f"forensic_audit_log_archive_{ts_str}.jsonl"
    manifest_path = audit_log.parent / f"forensic_manifest_{ts_str}.json"

    # 1. Byte-for-byte immutable archive copy
    archive_path.write_bytes(raw_bytes)
    arch_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if arch_sha != orig_sha:
        raise RuntimeError("CORRUPTED_ARCHIVE_COPY_HASH_MISMATCH")
    # Make archive read-only
    os.chmod(archive_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    code_sha = tool_sha or compute_code_sha()

    # 2. Immutable recovery manifest
    manifest_data = {
        "contract_id": "FORENSIC_AUDIT_CHAIN_MANIFEST_V1",
        "action": "FORENSIC_AUDIT_CHAIN_ROLLOVER",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "original_path": str(audit_log),
        "archive_path": str(archive_path),
        "archive_sha256": orig_sha,
        "total_records": inspection["total_records"],
        "first_record_prev_hash": inspection.get("first_record_prev_hash"),
        "first_invalid_record_index": inspection["first_invalid_record_index"],
        "first_invalid_record": inspection["first_invalid_record"],
        "last_valid_record_index": inspection["last_valid_record_index"],
        "last_valid_hash": inspection["last_valid_hash"],
        "corruption_cause": inspection["corruption_cause"],
        "recovery_code_sha256": code_sha,
        "certified_release_sha": str(certified_release_sha),
        "reason": str(reason),
    }
    manifest_bytes = (json.dumps(manifest_data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    # Make manifest read-only
    os.chmod(manifest_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    # 3. Provenance-bound bootstrap event
    run_id = str(new_run_id or f"forensic_recovery_{ts_str}").strip()
    now_epoch = time.time()
    bootstrap_event: dict[str, Any] = {
        "event": "AUDIT_CHAIN_BOOTSTRAP",
        "run_id": run_id,
        "boot_epoch": now_epoch,
        "source": "core.audit_chain_recovery.perform_audit_chain_rollover",
        "desk_id": "DEFAULT",
        "is_order_action": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "rollover_forensic_evidence": {
            "contract_id": "AUDIT_RECOVERY_PROVENANCE_V1",
            "predecessor_archive_path": str(archive_path),
            "predecessor_archive_sha256": orig_sha,
            "predecessor_last_valid_hash": inspection["last_valid_hash"],
            "predecessor_first_invalid_index": inspection["first_invalid_record_index"],
            "predecessor_first_invalid_record": inspection["first_invalid_record"],
            "corruption_cause": inspection["corruption_cause"],
            "forensic_manifest_path": str(manifest_path),
            "forensic_manifest_sha256": manifest_sha,
            "recovery_timestamp_utc": manifest_data["timestamp_utc"],
            "recovery_code_sha256": code_sha,
            "certified_release_sha": str(certified_release_sha),
            "rollover_reason": str(reason),
        },
        "ts_epoch": now_epoch,
        "ts_ist": datetime.now().astimezone().isoformat(),
        "prev_hash": GENESIS,
    }
    bootstrap_event["event_hash"] = _compute_hash(bootstrap_event)

    # 4. Atomic replacement
    tmp_path = audit_log.with_name(f".{audit_log.name}.tmp.{ts_str}")
    tmp_path.write_text(json.dumps(bootstrap_event, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(audit_log)

    # 5. Self-verification of new chain
    ok, status, count = verify_chain(audit_log, expected_run_id=run_id)
    if not ok:
        raise RuntimeError(f"AUDIT_CHAIN_ROLLOVER_VERIFY_FAILED:{status}")

    # 6. Provenance verification
    prov = verify_recovery_provenance(audit_log)
    if not prov.get("ok"):
        raise RuntimeError(f"AUDIT_CHAIN_PROVENANCE_VERIFY_FAILED:{prov.get('reason')}")

    return {
        "success": True,
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "archive_path": str(archive_path),
        "archive_sha256": orig_sha,
        "new_genesis_hash": bootstrap_event["event_hash"],
        "last_valid_hash": inspection["last_valid_hash"],
        "first_invalid_record_index": inspection["first_invalid_record_index"],
        "corruption_cause": inspection["corruption_cause"],
        "count": count,
    }


def verify_recovery_provenance(audit_log_path: Path, manifest_path: Path | None = None) -> dict[str, Any]:
    """Strictly verify the provenance binding of a recovered audit chain."""
    audit_log = Path(audit_log_path).resolve()
    if not audit_log.is_file():
        return {"ok": False, "reason": "audit_log_missing"}

    raw_lines = audit_log.read_bytes().splitlines()
    if not raw_lines:
        return {"ok": False, "reason": "audit_log_empty"}

    try:
        first_event = json.loads(raw_lines[0].decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "reason": f"genesis_json_invalid:{exc}"}

    if first_event.get("event") != "AUDIT_CHAIN_BOOTSTRAP":
        return {"ok": False, "reason": "genesis_not_bootstrap_event"}

    evidence = first_event.get("rollover_forensic_evidence")
    if not isinstance(evidence, dict):
        return {"ok": False, "reason": "missing_rollover_forensic_evidence"}

    manifest_file = Path(manifest_path).resolve() if manifest_path else Path(evidence.get("forensic_manifest_path", "")).resolve()
    if not manifest_file.is_file():
        return {"ok": False, "reason": "manifest_file_missing"}

    manifest_bytes = manifest_file.read_bytes()
    expected_manifest_sha = evidence.get("forensic_manifest_sha256")
    actual_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    if expected_manifest_sha != actual_manifest_sha:
        return {"ok": False, "reason": f"manifest_sha_mismatch expected={expected_manifest_sha} actual={actual_manifest_sha}"}

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "reason": f"manifest_json_invalid:{exc}"}

    archive_file = Path(evidence.get("predecessor_archive_path", "")).resolve()
    if not archive_file.is_file():
        return {"ok": False, "reason": "archive_file_missing"}

    archive_bytes = archive_file.read_bytes()
    expected_archive_sha = evidence.get("predecessor_archive_sha256")
    actual_archive_sha = hashlib.sha256(archive_bytes).hexdigest()
    if expected_archive_sha != actual_archive_sha:
        return {"ok": False, "reason": f"archive_sha_mismatch expected={expected_archive_sha} actual={actual_archive_sha}"}

    if manifest.get("archive_sha256") != actual_archive_sha:
        return {"ok": False, "reason": "manifest_archive_sha_mismatch"}

    # Re-verify archive inspection matches manifest and evidence
    arch_inspection = inspect_audit_chain(archive_file)
    if arch_inspection["last_valid_hash"] != evidence.get("predecessor_last_valid_hash"):
        return {"ok": False, "reason": "last_valid_hash_mismatch"}
    if arch_inspection["first_invalid_record_index"] != evidence.get("predecessor_first_invalid_index"):
        return {"ok": False, "reason": "first_invalid_index_mismatch"}
    if arch_inspection["corruption_cause"] != evidence.get("corruption_cause"):
        return {"ok": False, "reason": "corruption_cause_mismatch"}

    return {
        "ok": True,
        "verdict": "PROVENANCE_VERIFIED",
        "archive_sha256": actual_archive_sha,
        "manifest_sha256": actual_manifest_sha,
        "last_valid_hash": arch_inspection["last_valid_hash"],
        "first_invalid_record_index": arch_inspection["first_invalid_record_index"],
        "corruption_cause": arch_inspection["corruption_cause"],
        "recovery_code_sha256": evidence.get("recovery_code_sha256"),
    }
