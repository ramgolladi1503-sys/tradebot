from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class BundleError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_under_root(root: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise BundleError("artifact path must be a non-empty relative path")
    root_resolved = root.resolve()
    candidate = (root_resolved / relative_path).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise BundleError(f"artifact path escapes bundle root: {relative_path}") from exc
    return candidate


@dataclass(frozen=True)
class CertificationBundle:
    root: Path
    manifest: dict[str, Any]

    @classmethod
    def load(cls, root: str | Path) -> "CertificationBundle":
        bundle_root = Path(root).expanduser().resolve()
        manifest_path = bundle_root / "bundle_manifest.json"
        if not bundle_root.is_dir():
            raise BundleError(f"bundle directory not found: {bundle_root}")
        if not manifest_path.is_file():
            raise BundleError("bundle_manifest.json is missing")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BundleError(f"invalid bundle manifest: {exc}") from exc
        if not isinstance(manifest, dict):
            raise BundleError("bundle manifest must be a JSON object")
        return cls(root=bundle_root, manifest=manifest)

    @property
    def artifacts(self) -> dict[str, str]:
        value = self.manifest.get("artifacts", {})
        return value if isinstance(value, dict) else {}

    def artifact_path(self, name: str) -> Path:
        return resolve_under_root(self.root, name)

    def read_json(self, name: str) -> dict[str, Any]:
        path = self.artifact_path(name)
        if not path.is_file():
            raise BundleError(f"required artifact missing: {name}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BundleError(f"invalid JSON artifact {name}: {exc}") from exc
        if not isinstance(payload, dict):
            raise BundleError(f"artifact must be a JSON object: {name}")
        return payload

    def digest(self) -> str:
        payload = {
            "manifest": self.manifest,
            "observed_hashes": {
                name: sha256_file(self.artifact_path(name))
                for name in sorted(self.artifacts)
                if self.artifact_path(name).is_file()
            },
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
