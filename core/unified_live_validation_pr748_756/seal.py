"""Hash and seal unified campaign evidence directories."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seal_evidence_root(root: Path) -> dict[str, Any]:
    if (root / "SEALED").exists():
        raise RuntimeError("evidence_root_already_sealed")
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {"SHA256SUMS", "artifact_manifest.json", "SEALED"}:
            continue
        files.append({"path": str(path.relative_to(root)), "sha256": sha256_file(path), "bytes": path.stat().st_size})
    manifest = {"artifact_count": len(files), "artifacts": files}
    (root / "artifact_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sums = "".join(f"{item['sha256']}  {item['path']}\n" for item in files)
    (root / "SHA256SUMS").write_text(sums, encoding="utf-8")
    manifest["artifact_manifest_sha256"] = sha256_file(root / "artifact_manifest.json")
    (root / "SEALED").write_text(json.dumps({"sealed": True, "artifact_manifest_sha256": manifest["artifact_manifest_sha256"]}, sort_keys=True) + "\n", encoding="utf-8")
    return manifest

