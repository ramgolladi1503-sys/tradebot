from __future__ import annotations

from pathlib import Path


def build_adapter_sha(repo_root: Path, path: str) -> str:
    target = repo_root / path
    return _sha256(target) if target.exists() else ""


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
