from __future__ import annotations

import hashlib
from pathlib import Path

from core.external_artifacts import ArtifactManifest, resolve_local


def _manifest(data: bytes) -> ArtifactManifest:
    return ArtifactManifest("fixture", "local", hashlib.sha256(data).hexdigest(), len(data), 1)


def test_missing_artifact_fails_closed(tmp_path: Path) -> None:
    result = resolve_local(_manifest(b"expected"), tmp_path / "missing", tmp_path / "cache")
    assert result.status == "BLOCKED_EXTERNAL_DATA"
    assert result.path is None
    assert result.observed_sha256 == "MISSING"


def test_verified_source_installs_atomically(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"expected")
    result = resolve_local(_manifest(b"expected"), source, tmp_path / "cache")
    assert result.status == "RESOLVED_LOCAL"
    assert result.path is not None and result.path.read_bytes() == b"expected"


def test_hash_mismatch_is_not_accepted(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"wrong")
    result = resolve_local(_manifest(b"expected"), source, tmp_path / "cache")
    assert result.status == "BLOCKED_EXTERNAL_DATA"


def test_verified_cache_is_reused(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    cached = cache / "fixture"
    cached.write_bytes(b"expected")
    result = resolve_local(_manifest(b"expected"), tmp_path / "missing", cache)
    assert result.status == "RESOLVED_LOCAL"
    assert result.path == cached
