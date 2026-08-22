"""Fail-closed resolution of large immutable external artifacts.

This module is intentionally backend-neutral. It does not authenticate to, or
download from, Google Drive; a future backend must provide verified bytes.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ArtifactStatus = Literal["RESOLVED_LOCAL", "BLOCKED_EXTERNAL_DATA"]


@dataclass(frozen=True)
class ArtifactManifest:
    dataset_id: str
    storage: str
    sha256: str
    bytes: int
    schema_version: int
    required_for: tuple[str, ...] = ()
    drive_file_id: str | None = None


@dataclass(frozen=True)
class ArtifactResolution:
    status: ArtifactStatus
    path: Path | None
    expected_sha256: str
    observed_sha256: str | Literal["MISSING"]
    expected_bytes: int
    observed_bytes: int | Literal["MISSING"]
    reason: str | None = None


def _digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def resolve_local(manifest: ArtifactManifest, source: Path, cache_dir: Path) -> ArtifactResolution:
    """Verify source or cache and atomically install a verified cache entry.

    Missing or invalid data is an explicit blocked result; it is never treated
    as an empty dataset or a successful zero-observation run.
    """
    target = cache_dir / manifest.dataset_id
    candidates = (target, source)
    for candidate in candidates:
        if not candidate.is_file():
            continue
        observed_bytes, observed_sha256 = _digest(candidate)
        if observed_bytes != manifest.bytes or observed_sha256 != manifest.sha256:
            continue
        if candidate == target:
            return ArtifactResolution("RESOLVED_LOCAL", target, manifest.sha256, observed_sha256, manifest.bytes, observed_bytes)
        cache_dir.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{manifest.dataset_id}.", dir=cache_dir)
        os.close(fd)
        try:
            shutil.copyfile(candidate, temporary)
            installed = Path(temporary)
            installed.replace(target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return ArtifactResolution("RESOLVED_LOCAL", target, manifest.sha256, observed_sha256, manifest.bytes, observed_bytes)
    return ArtifactResolution(
        "BLOCKED_EXTERNAL_DATA", None, manifest.sha256, "MISSING", manifest.bytes, "MISSING",
        "verified local artifact unavailable; external retrieval is not configured",
    )
