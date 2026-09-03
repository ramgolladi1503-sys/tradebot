"""Durable, fail-closed evidence contract for offline certification sessions."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


UNKNOWN = "UNKNOWN"
AUTHORITY_FALSE = {
    "broker_write_authority": False,
    "order_authority": False,
    "paper_authorized": False,
    "live_authorized": False,
}


@dataclass(frozen=True)
class OfflineSessionEvidence:
    session_id: str
    session_date: str
    release_sha: str
    worktree_root: str
    runtime_root: str
    start_ist: str = UNKNOWN
    stop_ist: str = UNKNOWN
    start_utc: str = UNKNOWN
    stop_utc: str = UNKNOWN
    authority_artifact_hashes: Mapping[str, str] = field(default_factory=dict)
    metrics: Mapping[str, Any] = field(default_factory=dict)
    shutdown: Mapping[str, Any] = field(default_factory=dict)
    broker_counters: Mapping[str, Any] = field(default_factory=lambda: {
        "broker_write_calls": 0,
        "broker_order_calls": 0,
        "orders_placed": 0,
        "orders_modified": 0,
        "orders_cancelled": 0,
    })

    def payload(self) -> dict[str, Any]:
        for name in ("session_id", "session_date", "release_sha", "worktree_root", "runtime_root"):
            if not str(getattr(self, name) or "").strip():
                raise ValueError(f"session_identity_missing:{name}")
        return {
            "schema_version": 1,
            "session_id": self.session_id,
            "session_date": self.session_date,
            "release_sha": self.release_sha,
            "worktree_root": self.worktree_root,
            "runtime_root": self.runtime_root,
            "start_ist": self.start_ist or UNKNOWN,
            "stop_ist": self.stop_ist or UNKNOWN,
            "start_utc": self.start_utc or UNKNOWN,
            "stop_utc": self.stop_utc or UNKNOWN,
            "authority_artifact_hashes": dict(self.authority_artifact_hashes),
            "metrics": dict(self.metrics),
            "shutdown": dict(self.shutdown),
            "broker_counters": dict(self.broker_counters),
            **AUTHORITY_FALSE,
        }


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_final_session_manifest(path: str | Path, evidence: OfflineSessionEvidence) -> str:
    """Atomically write the final manifest and its adjacent SHA-256 sidecar."""
    payload = evidence.payload()
    raw = _canonical_bytes(payload)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, destination)
    digest = hashlib.sha256(raw).hexdigest()
    sidecar = destination.with_name(destination.name + ".sha256")
    side_tmp = sidecar.with_name(f".{sidecar.name}.{os.getpid()}.tmp")
    side_tmp.write_text(digest + "  " + destination.name + "\n", encoding="utf-8")
    os.replace(side_tmp, sidecar)
    return digest


def independently_verify_session_manifest(path: str | Path) -> dict[str, Any]:
    """Re-read the manifest and hash sidecar after the producing process exits."""
    destination = Path(path)
    raw = destination.read_bytes()
    payload = json.loads(raw)
    expected = hashlib.sha256(raw).hexdigest()
    sidecar = destination.with_name(destination.name + ".sha256")
    recorded = sidecar.read_text(encoding="utf-8").split()[0]
    if recorded != expected:
        raise ValueError("session_manifest_hash_mismatch")
    for key, value in AUTHORITY_FALSE.items():
        if payload.get(key) is not value:
            raise ValueError(f"session_manifest_authority_not_false:{key}")
    required = ("session_id", "session_date", "release_sha", "worktree_root", "runtime_root")
    missing = [key for key in required if not str(payload.get(key) or "").strip()]
    if missing:
        raise ValueError("session_manifest_identity_missing:" + ",".join(missing))
    return {"ok": True, "sha256": expected, "payload": payload}
