"""Fail-closed identity contract for one canonical read-only live session."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import json
import os
from typing import Any, Mapping


AUTHORITY_FALSE = {
    "broker_write_authority": False,
    "order_authority": False,
    "paper_authorized": False,
    "live_authorized": False,
}


@dataclass(frozen=True)
class LiveSessionManifest:
    session_date: str
    session_id: str
    source_sha: str
    observer_sha: str
    observer_pid: int | None
    runtime_root: str
    sqlite_path: str
    instrument_master_path: str
    instrument_master_sha: str | None
    auth_state: str
    feed_state: str
    persistence_state: str
    subscription_count: int | None
    consumer_registry: tuple[str, ...] = field(default_factory=tuple)
    pipeline_sha: str | None = None
    consumer_registry_path: str | None = None
    advisory_queue_path: str | None = None
    authority: Mapping[str, bool] = field(default_factory=lambda: dict(AUTHORITY_FALSE))

    def validate(self) -> None:
        for name in ("session_date", "session_id", "source_sha", "observer_sha", "runtime_root", "sqlite_path"):
            if not str(getattr(self, name) or "").strip():
                raise ValueError(f"manifest_missing_{name}")
        for key, expected in AUTHORITY_FALSE.items():
            if self.authority.get(key) is not expected:
                raise ValueError(f"manifest_authority_not_false:{key}")
        if self.subscription_count is not None and self.subscription_count < 0:
            raise ValueError("manifest_subscription_count_negative")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": 1,
            "session_date": self.session_date,
            "session_id": self.session_id,
            "source_sha": self.source_sha,
            "observer_sha": self.observer_sha,
            "observer_pid": self.observer_pid,
            "runtime_root": self.runtime_root,
            "sqlite_path": self.sqlite_path,
            "instrument_master_path": self.instrument_master_path,
            "instrument_master_sha": self.instrument_master_sha,
            "auth_state": self.auth_state,
            "feed_state": self.feed_state,
            "persistence_state": self.persistence_state,
            "subscription_count": self.subscription_count,
            "consumer_registry": sorted(set(self.consumer_registry)),
            "pipeline_sha": self.pipeline_sha,
            "consumer_registry_path": self.consumer_registry_path,
            "advisory_queue_path": self.advisory_queue_path,
            **AUTHORITY_FALSE,
        }


def write_session_manifest(path: str | Path, manifest: LiveSessionManifest) -> str:
    """Atomically write a manifest and return its SHA-256 without secrets."""
    payload = json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + f".{os.getpid()}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, destination)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_session_manifest(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    for key, expected in AUTHORITY_FALSE.items():
        if payload.get(key) is not expected:
            raise ValueError(f"manifest_authority_not_false:{key}")
    if not payload.get("session_id") or not payload.get("source_sha"):
        raise ValueError("manifest_identity_missing")
    return payload
