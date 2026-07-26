from __future__ import annotations

import base64
import gzip
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from research.option_analytics_v1.evidence import publication_gate

REFERENCE_JSON = "reference_case_results.json"
REFERENCE_PACKAGE = "reference_case_results.json.gz.b64"
EXPECTED_REFERENCE_SHA256 = "1b305ed9fb9fa6e21c51ec164be661e5964240d9e489788f5408a9bcc7f8d9ed"
EXPECTED_PACKAGE_SHA256 = "0bb9d38316302141bbb6b7a4a7a69c7c790c9a99d7d69a682c631b7aff1a7de1"
STATIC_JSON_ARTIFACTS = (
    "bundle_summary.json",
    "determinism_report.json",
    "legacy_compatibility_audit.json",
    "publication_gate.json",
    "run_manifest.json",
)


def package_reference_artifact(evidence_dir: str | Path, *, remove_plaintext: bool = False) -> dict[str, Any]:
    source_dir = Path(evidence_dir)
    source = source_dir / REFERENCE_JSON
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    encoded = base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)) + b"\n"
    target = source_dir / REFERENCE_PACKAGE
    target.write_bytes(encoded)
    if remove_plaintext:
        source.unlink()
    return {
        "schema_version": "1.0.0",
        "reference_json_sha256": digest,
        "package_sha256": hashlib.sha256(encoded).hexdigest(),
        "uncompressed_bytes": len(raw),
        "package_bytes": len(encoded),
    }


def materialize_committed_bundle(source_dir: str | Path, target_dir: str | Path) -> Path:
    source = Path(source_dir)
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    for name in STATIC_JSON_ARTIFACTS:
        shutil.copy2(source / name, target / name)
    package_bytes = (source / REFERENCE_PACKAGE).read_bytes()
    package_digest = hashlib.sha256(package_bytes).hexdigest()
    if package_digest != EXPECTED_PACKAGE_SHA256:
        raise ValueError(f"reference package digest mismatch: {package_digest}")
    encoded = package_bytes.strip()
    raw = gzip.decompress(base64.b64decode(encoded, validate=True))
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_REFERENCE_SHA256:
        raise ValueError(f"reference evidence digest mismatch: {digest}")
    payload = json.loads(raw)
    if payload.get("failure_count") != 0 or payload.get("input_case_count") != 96:
        raise ValueError("packaged reference evidence contract failed")
    (target / REFERENCE_JSON).write_bytes(raw)
    _write_sha256s(target)
    return target


def verify_committed_bundle(repo_root: str | Path, source_dir: str | Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        materialized = materialize_committed_bundle(source_dir, tmp)
        gate = publication_gate(repo_root, materialized)
        gate["packaged_reference_sha256"] = EXPECTED_REFERENCE_SHA256
        gate["packaged_reference_verified"] = gate["verdict"] == "PASS_RESEARCH_SIDECAR_GATE"
        return gate


def _write_sha256s(target: Path) -> None:
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(target.glob("*.json"))
    ]
    (target / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
