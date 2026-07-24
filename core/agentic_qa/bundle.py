from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AuditBundleError(ValueError):
    pass


_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")


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
        raise AuditBundleError("artifact path must be a non-empty relative path")
    root_resolved = root.resolve()
    candidate = (root_resolved / relative_path).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise AuditBundleError(f"artifact path escapes bundle root: {relative_path}") from exc
    return candidate


@dataclass(frozen=True)
class AuditBundle:
    root: Path
    manifest: dict[str, Any]
    manifest_name: str

    @classmethod
    def load(cls, root: str | Path) -> "AuditBundle":
        bundle_root = Path(root).expanduser().resolve()
        if not bundle_root.is_dir():
            raise AuditBundleError(f"bundle directory not found: {bundle_root}")
        candidates = ("run_manifest.json", "bundle_manifest.json")
        manifest_path = next((bundle_root / name for name in candidates if (bundle_root / name).is_file()), None)
        if manifest_path is None:
            raise AuditBundleError("run_manifest.json or bundle_manifest.json is required")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuditBundleError(f"invalid manifest: {exc}") from exc
        if not isinstance(manifest, dict):
            raise AuditBundleError("manifest must be a JSON object")
        return cls(root=bundle_root, manifest=manifest, manifest_name=manifest_path.name)

    @property
    def artifacts(self) -> dict[str, dict[str, str]]:
        raw = self.manifest.get("artifacts", {})
        if not isinstance(raw, dict):
            return {}
        normalized: dict[str, dict[str, str]] = {}
        for logical_name, value in raw.items():
            if isinstance(value, str):
                logical_text = str(logical_name)
                if _SHA256.fullmatch(value):
                    normalized[logical_text] = {"path": logical_text, "sha256": value.lower()}
                else:
                    normalized[logical_text] = {"path": value}
            elif isinstance(value, dict):
                path = value.get("path") or value.get("artifact") or logical_name
                normalized[str(logical_name)] = {
                    "path": str(path),
                    "sha256": str(value.get("sha256") or ""),
                }
        return normalized

    def observed_artifacts(self) -> dict[str, dict[str, str | bool]]:
        output: dict[str, dict[str, str | bool]] = {}
        for logical_name, metadata in sorted(self.artifacts.items()):
            relative = metadata.get("path", "")
            try:
                path = resolve_under_root(self.root, relative)
                exists = path.is_file()
                observed = sha256_file(path) if exists else "MISSING"
                output[logical_name] = {
                    "path": relative,
                    "safe": True,
                    "exists": exists,
                    "expected_sha256": metadata.get("sha256", ""),
                    "observed_sha256": observed,
                }
            except AuditBundleError:
                output[logical_name] = {
                    "path": relative,
                    "safe": False,
                    "exists": False,
                    "expected_sha256": metadata.get("sha256", ""),
                    "observed_sha256": "UNSAFE_PATH",
                }
        return output

    def read_json_artifacts(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for logical_name, metadata in sorted(self.artifacts.items()):
            relative = metadata.get("path", "")
            if not relative.lower().endswith(".json"):
                continue
            try:
                path = resolve_under_root(self.root, relative)
            except AuditBundleError:
                continue
            if not path.is_file():
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            payload[logical_name] = value
        return payload

    def digest(self) -> str:
        payload = {
            "manifest": self.manifest,
            "observed_artifacts": self.observed_artifacts(),
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
