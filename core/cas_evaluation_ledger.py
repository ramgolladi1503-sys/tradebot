"""Atomic session-scoped idempotency ledger for read-only CAS evaluation."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

MAX_INDEX_BYTES = 2 * 1_048_576
MAX_ENTRIES = 2048
MAX_RECEIPT_BYTES = 16_384
AUTHORITY = {
    "read_only": True,
    "append": False,
    "is_order_action": False,
    "broker_api_called": False,
    "allowed_for_live_execution": False,
}


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _atomic_replace(path: Path, payload: Mapping[str, Any], *, max_bytes: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(dict(payload), sort_keys=True, indent=2,
        ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError("CAS_EVALUATION_ARTIFACT_BOUND_EXCEEDED")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class CASEvaluationLedger:
    """Serialize claims and completed evaluation receipts for one session."""

    def __init__(self, root: str | Path, *, session_identity: Mapping[str, Any],
                 lease_seconds: float = 120.0, lock_timeout_seconds: float = 2.0):
        if not isinstance(session_identity, Mapping) or not all(
                session_identity.get(name) for name in
                ("trading_date", "venue", "calendar_id", "calendar_version")):
            raise ValueError("CAS_EVALUATION_SESSION_IDENTITY_REQUIRED")
        self.root = Path(root).resolve()
        self.session_identity = dict(session_identity)
        self.lease_seconds = max(1.0, float(lease_seconds))
        self.lock_timeout_seconds = max(0.0, float(lock_timeout_seconds))
        self.index_path = self.root / "cas-evaluation-index-v1.json"
        self.lock_path = self.root / ".cas-evaluation-index-v1.lock"

    def _locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        deadline = time.monotonic() + self.lock_timeout_seconds
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise TimeoutError("CAS_EVALUATION_LOCK_TIMEOUT")
                time.sleep(0.01)

    def _load(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"schema_version": 1, "session_identity": self.session_identity,
                "entries": [], "index_sha256": _canonical_hash({
                    "schema_version": 1, "session_identity": self.session_identity,
                    "entries": []})}
        if self.index_path.stat().st_size > MAX_INDEX_BYTES:
            raise ValueError("CAS_EVALUATION_INDEX_SIZE_BOUND_EXCEEDED")
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1 or payload.get("session_identity") != self.session_identity:
            raise ValueError("CAS_EVALUATION_INDEX_IDENTITY_OR_SCHEMA_MISMATCH")
        entries = payload.get("entries")
        if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
            raise ValueError("CAS_EVALUATION_ENTRY_BOUND_EXCEEDED")
        expected = _canonical_hash({"schema_version": 1,
            "session_identity": self.session_identity, "entries": entries})
        if payload.get("index_sha256") != expected:
            raise ValueError("CAS_EVALUATION_INDEX_HASH_MISMATCH")
        if any(not isinstance(row, Mapping) or not isinstance(row.get("evaluation_identity_sha256"), str)
                or len(row["evaluation_identity_sha256"]) != 64
                or row.get("status") not in {"CLAIMED", "COMPLETED"}
                for row in entries):
            raise ValueError("CAS_EVALUATION_INDEX_ENTRY_INVALID")
        return payload

    def _save(self, entries: list[dict[str, Any]]) -> None:
        body = {"schema_version": 1, "session_identity": self.session_identity,
            "entries": sorted(entries, key=lambda row: row["evaluation_identity_sha256"])}
        _atomic_replace(self.index_path, {**body, "index_sha256": _canonical_hash(body)},
            max_bytes=MAX_INDEX_BYTES)

    def _receipt(self, key: str) -> dict[str, Any] | None:
        path = self.root / f"cas-evaluation-{key}.json"
        if not path.is_file():
            return None
        if path.stat().st_size > MAX_RECEIPT_BYTES:
            raise ValueError("CAS_EVALUATION_RECEIPT_SIZE_BOUND_EXCEEDED")
        receipt = json.loads(path.read_text(encoding="utf-8"))
        body = {name: value for name, value in receipt.items() if name != "receipt_sha256"}
        if (receipt.get("evaluation_identity_sha256") != key
                or receipt.get("session_identity") != self.session_identity
                or receipt.get("receipt_sha256") != _canonical_hash(body)):
            raise ValueError("CAS_EVALUATION_RECEIPT_INVALID")
        return receipt

    def claim(self, *, evaluation_identity_sha256: str, run_id: str,
              source_event_sha256s: list[str], source_sha: str,
              now_epoch: float | None = None) -> dict[str, Any]:
        key = evaluation_identity_sha256
        if (not isinstance(key, str) or len(key) != 64
                or any(char not in "0123456789abcdef" for char in key)
                or not run_id or not source_event_sha256s
                or any(not isinstance(item, str) or len(item) != 64
                    or any(char not in "0123456789abcdef" for char in item)
                    for item in source_event_sha256s)):
            return {"status": "BLOCKED", "reason": "CAS_EVALUATION_IDENTITY_INVALID", **AUTHORITY}
        now = float(now_epoch if now_epoch is not None else time.time())
        fd = self._locked()
        try:
            try:
                index = self._load()
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                return {"status": "BLOCKED", "reason": str(exc) or "CAS_EVALUATION_INDEX_INVALID", **AUTHORITY}
            entries = [dict(row) for row in index["entries"]]
            by_identity = {row["evaluation_identity_sha256"]: row for row in entries}
            prior = by_identity.get(key)
            receipt = self._receipt(key)
            expected_events = sorted(set(source_event_sha256s))
            if prior is not None and sorted(prior.get("source_event_sha256s", [])) != expected_events:
                return {"status": "BLOCKED", "reason": "CAS_EVALUATION_SOURCE_IDENTITY_CONFLICT", **AUTHORITY}
            if receipt is not None:
                if (receipt.get("source_event_sha256s") != expected_events
                        or receipt.get("source_sha") != source_sha):
                    return {"status": "BLOCKED", "reason": "CAS_EVALUATION_RECEIPT_SOURCE_MISMATCH", **AUTHORITY}
                if prior is None or prior.get("status") != "COMPLETED":
                    recovered = {"evaluation_identity_sha256": key,
                        "status": "COMPLETED", "run_id": receipt["run_id"],
                        "claim_generation": int(prior.get("claim_generation", 1)) if prior else 1,
                        "source_event_sha256s": expected_events,
                        "receipt_sha256": receipt["receipt_sha256"],
                        "updated_epoch": now}
                    entries = [row for row in entries if row["evaluation_identity_sha256"] != key]
                    entries.append(recovered)
                    self._save(entries)
                return {"status": "DUPLICATE_COMPLETED", "receipt": receipt, **AUTHORITY}
            if prior is not None and prior.get("status") == "COMPLETED":
                raise ValueError("CAS_EVALUATION_COMPLETED_RECEIPT_MISSING")
            if prior is not None and now - float(prior.get("claimed_epoch", now)) < self.lease_seconds:
                return {"status": "DUPLICATE_IN_PROGRESS", "run_id": prior.get("run_id"), **AUTHORITY}
            if prior is None and len(entries) >= MAX_ENTRIES:
                return {"status": "BLOCKED", "reason": "CAS_EVALUATION_ENTRY_BOUND_EXCEEDED", **AUTHORITY}
            generation = int(prior.get("claim_generation", 0)) + 1 if prior else 1
            new_entry = {"evaluation_identity_sha256": key, "status": "CLAIMED",
                "run_id": run_id, "claim_generation": generation,
                "claimed_epoch": now, "source_event_sha256s": expected_events}
            entries = [row for row in entries if row["evaluation_identity_sha256"] != key]
            entries.append(new_entry)
            self._save(entries)
            return {"status": "CLAIMED", "claim_generation": generation, **AUTHORITY}
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def complete(self, *, evaluation_identity_sha256: str, run_id: str,
                 claim_generation: int, source_sha: str,
                 source_event_sha256s: list[str], decision: Mapping[str, Any],
                 completed_epoch: float | None = None) -> dict[str, Any]:
        key = evaluation_identity_sha256
        fd = self._locked()
        try:
            index = self._load()
            entries = [dict(row) for row in index["entries"]]
            prior = next((row for row in entries if row["evaluation_identity_sha256"] == key), None)
            if (prior is None or prior.get("status") != "CLAIMED"
                    or prior.get("run_id") != run_id
                    or prior.get("claim_generation") != claim_generation):
                return {"status": "BLOCKED", "reason": "CAS_EVALUATION_CLAIM_MISMATCH", **AUTHORITY}
            decision_body = dict(decision)
            receipt_body = {"schema_version": 1,
                "evaluation_identity_sha256": key,
                "session_identity": self.session_identity,
                "run_id": run_id, "source_sha": source_sha,
                "source_event_sha256s": sorted(set(source_event_sha256s)),
                "decision_sha256": _canonical_hash(decision_body),
                "direction": decision_body.get("direction"),
                "completed_epoch": float(completed_epoch if completed_epoch is not None else time.time()),
                **AUTHORITY}
            receipt = {**receipt_body, "receipt_sha256": _canonical_hash(receipt_body)}
            receipt_path = self.root / f"cas-evaluation-{key}.json"
            if receipt_path.exists():
                existing = self._receipt(key)
                if (existing.get("session_identity") != self.session_identity
                        or existing.get("run_id") != run_id
                        or existing.get("source_sha") != source_sha
                        or existing.get("source_event_sha256s") != sorted(set(source_event_sha256s))
                        or existing.get("decision_sha256") != receipt["decision_sha256"]):
                    return {"status": "BLOCKED", "reason": "CAS_EVALUATION_RECEIPT_CONFLICT", **AUTHORITY}
                receipt = existing
            else:
                _atomic_replace(receipt_path, receipt, max_bytes=MAX_RECEIPT_BYTES)
            completed = {"evaluation_identity_sha256": key, "status": "COMPLETED",
                "run_id": run_id, "claim_generation": claim_generation,
                "source_event_sha256s": sorted(set(source_event_sha256s)),
                "receipt_sha256": receipt["receipt_sha256"],
                "updated_epoch": receipt_body["completed_epoch"]}
            entries = [row for row in entries if row["evaluation_identity_sha256"] != key]
            entries.append(completed)
            self._save(entries)
            return {"status": "COMPLETED", "receipt": receipt, **AUTHORITY}
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def release_claim(self, *, evaluation_identity_sha256: str, run_id: str,
                      claim_generation: int) -> dict[str, Any]:
        """Release a failed pure-evaluation claim without emitting a receipt."""
        fd = self._locked()
        try:
            index = self._load()
            entries = [dict(row) for row in index["entries"]]
            prior = next((row for row in entries
                if row["evaluation_identity_sha256"] == evaluation_identity_sha256), None)
            if (prior is None or prior.get("status") != "CLAIMED"
                    or prior.get("run_id") != run_id
                    or prior.get("claim_generation") != claim_generation):
                return {"status": "BLOCKED", "reason": "CAS_EVALUATION_CLAIM_MISMATCH", **AUTHORITY}
            entries = [row for row in entries
                if row["evaluation_identity_sha256"] != evaluation_identity_sha256]
            self._save(entries)
            return {"status": "RELEASED", **AUTHORITY}
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
