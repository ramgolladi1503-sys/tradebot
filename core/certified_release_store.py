"""Durable release-selection journal. This module grants no execution authority.

The store persists decisions, not certification: a caller must independently
verify candidate evidence before asking to record a promotion. Readers verify
all committed history; interrupted writes may leave unreferenced audit records.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class ReleaseStoreError(ValueError):
    """Invalid, conflicting, or corrupt release state."""


def canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value: dict) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _sha(value: object) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ReleaseStoreError("invalid_exact_sha")


def _sync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class ReleaseStore:
    """Single-host filesystem journal with serialized compare-and-swap writes.

    Root ownership and permissions are an operator trust boundary. Hashes detect
    accidental corruption, not malicious rewriting by the directory owner.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        if self.root.is_symlink():
            raise ReleaseStoreError("symlink_store_root")
        self.history = self.root / "history"
        self.pointer = self.root / "current.json"

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.history.mkdir(exist_ok=True, mode=0o700)
        if self.history.is_symlink():
            raise ReleaseStoreError("symlink_history")
        fd = os.open(self.root / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            # Nonblocking: contention fails closed instead of hanging automation.
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ReleaseStoreError("store_busy_retry") from exc
            yield
        finally:
            os.close(fd)

    def read(self) -> dict | None:
        if not self.pointer.exists():
            return None
        if self.pointer.is_symlink():
            raise ReleaseStoreError("symlink_pointer")
        try:
            pointer = json.loads(self.pointer.read_bytes())
            event_id = pointer["event_sha256"]
            seen: set[str] = set()
            latest = None
            child = None
            while event_id is not None:
                if not isinstance(event_id, str) or not re.fullmatch(r"[0-9a-f]{64}", event_id) or event_id in seen:
                    raise ReleaseStoreError("invalid_history_chain")
                seen.add(event_id)
                path = self.history / (event_id + ".json")
                if path.is_symlink():
                    raise ReleaseStoreError("symlink_event")
                event = json.loads(path.read_bytes())
                if digest(event) != event_id or event["schema_version"] != 1:
                    raise ReleaseStoreError("history_integrity_failed")
                _sha(event["certified_live_sha"])
                if event["fallback_live_sha"] is not None:
                    _sha(event["fallback_live_sha"])
                if child and child["fallback_live_sha"] != event["certified_live_sha"]:
                    raise ReleaseStoreError("fallback_chain_mismatch")
                if event["previous_event"] is None and event["fallback_live_sha"] is not None:
                    raise ReleaseStoreError("bootstrap_fallback_invalid")
                latest = latest or {**event, "event_sha256": event_id}
                child = event
                event_id = event["previous_event"]
            if latest is None:
                raise ReleaseStoreError("empty_history")
            return latest
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ReleaseStoreError("unreadable_release_history") from exc

    def record_verified_selection(self, *, candidate_sha: str, evidence_sha256: str,
                                  expected_event: str | None) -> dict:
        """Record a caller-verified selection, retaining the previous selection.

        This low-level method is not a public promotion gate. The certification
        engine must validate exact source and evidence before invoking it.
        """
        _sha(candidate_sha)
        if not isinstance(evidence_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", evidence_sha256) is None:
            raise ReleaseStoreError("invalid_evidence_digest")
        with self._lock():
            current = self.read()
            if (current or {}).get("event_sha256") != expected_event:
                raise ReleaseStoreError("concurrent_selection_changed")
            if current and current["certified_live_sha"] == candidate_sha:
                raise ReleaseStoreError("already_selected")
            event = {
                "schema_version": 1, "certified_live_sha": candidate_sha,
                "fallback_live_sha": current["certified_live_sha"] if current else None,
                "previous_event": expected_event, "evidence_sha256": evidence_sha256,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            event_id = digest(event)
            # Exclusive creation ensures a prior manifest can never be replaced.
            fd = os.open(self.history / (event_id + ".json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(canonical(event)); handle.flush(); os.fsync(handle.fileno())
            _sync(self.history)
            fd, name = tempfile.mkstemp(prefix=".current-", dir=self.root)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(canonical({"event_sha256": event_id})); handle.flush(); os.fsync(handle.fileno())
                os.replace(name, self.pointer)
                _sync(self.root)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
            return {**event, "event_sha256": event_id}
