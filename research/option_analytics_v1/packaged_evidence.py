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
EXPECTED_REFERENCE_SHA256 = "8ac3e16d73aab1ea2c5de648b5061ac06859f55a8018c38a576ff890cc5c7b00"
EXPECTED_PACKAGE_SHA256 = "9a53e2efc48e8e5cdef7f6c55fe2a87719eb0c793e1e38d20f3a43e99a36a34b"
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
    metadata = {
        "schema_version": "1.0.0",
        "reference_json_sha256": digest,
        "package_sha256": hashlib.sha256(encoded).hexdigest(),
        "reference_json_bytes": len(raw),
        "package_bytes": len(encoded),
        "package_filename": REFERENCE_PACKAGE,
    }
    (source_dir / "reference_package_manifest.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if remove_plaintext:
        source.unlink()
    _write_committed_sha256s(source_dir)
    return metadata


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


def verify_committed_hashes(source_dir: str | Path) -> list[str]:
    source = Path(source_dir)
    sums = source / "SHA256SUMS"
    if not sums.exists():
        return ["SHA256SUMS missing"]
    errors: list[str] = []
    for line in sums.read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        path = source / name
        if not path.exists():
            errors.append(f"missing committed artifact: {name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(f"committed hash mismatch: {name}")
    return errors


def verify_committed_bundle(repo_root: str | Path, source_dir: str | Path) -> dict[str, Any]:
    hash_errors = verify_committed_hashes(source_dir)
    if hash_errors:
        return {
            "schema_version": "1.0.0",
            "verdict": "FAIL_RESEARCH_SIDECAR_GATE",
            "failure_count": len(hash_errors),
            "errors": hash_errors,
            "packaged_reference_verified": False,
        }
    with tempfile.TemporaryDirectory() as tmp:
        materialized = materialize_committed_bundle(source_dir, tmp)
        gate = publication_gate(repo_root, materialized)
        gate["packaged_reference_sha256"] = EXPECTED_REFERENCE_SHA256
        gate["packaged_reference_verified"] = gate["verdict"] == "PASS_RESEARCH_SIDECAR_GATE"
        return gate


def _write_committed_sha256s(source: Path) -> None:
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(source.iterdir())
        if path.is_file() and path.name != "SHA256SUMS"
    ]
    (source / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_sha256s(target: Path) -> None:
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(target.glob("*.json"))
    ]
    (target / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
