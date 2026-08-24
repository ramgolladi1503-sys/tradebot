"""Provenance and close-seal contract for canonical live-session artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ArtifactRecord:
    path: str
    artifact_type: str
    sha256: str
    immutable: bool
    session_id: str
    source_sha: str

    def validate(self) -> None:
        if not self.path or not self.artifact_type or not self.session_id or not self.source_sha:
            raise ValueError("artifact_identity_missing")
        if len(self.sha256) != 64 or any(char not in "0123456789abcdef" for char in self.sha256):
            raise ValueError("artifact_sha256_invalid")
        if self.immutable is not True:
            raise ValueError("artifact_not_immutable")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_immutable_json(
    path: str | Path,
    payload: Mapping[str, Any],
    *,
    artifact_type: str,
    session_id: str,
    source_sha: str,
) -> ArtifactRecord:
    """Create an immutable JSON artifact; an existing path is never replaced."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"immutable_artifact_exists:{destination}")
    encoded = (json.dumps(dict(payload), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    temporary = destination.with_name(destination.name + f".{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        # Linking is deliberately used instead of replace: if another writer
        # wins the destination race, sealing fails rather than overwriting it.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    record = ArtifactRecord(
        path=str(destination), artifact_type=artifact_type,
        sha256=hashlib.sha256(encoded).hexdigest(), immutable=True,
        session_id=session_id, source_sha=source_sha,
    )
    record.validate()
    return record


def verify_artifact(record: ArtifactRecord) -> None:
    record.validate()
    path = Path(record.path)
    if not path.is_file():
        raise ValueError("immutable_artifact_missing")
    if sha256_file(path) != record.sha256:
        raise ValueError("immutable_artifact_hash_mismatch")
