from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import SAFETY_FIELDS, SCHEMA_VERSION, canonical_hash


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_code_sha(project_root: str | Path) -> str:
    environment_sha = os.environ.get("GITHUB_SHA", "").strip().lower()
    if len(environment_sha) == 40 and all(
        character in "0123456789abcdef" for character in environment_sha
    ):
        return environment_sha
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(project_root),
        check=True,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip().lower()
    if len(value) != 40 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError("unable to derive a valid Git commit SHA")
    return value


def envelope(
    payload: dict[str, Any],
    *,
    code_sha: str,
    input_hashes: dict[str, str],
    deterministic_seeds: list[int],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_commit_sha": code_sha,
        "input_hashes": dict(sorted(input_hashes.items())),
        "deterministic_seeds": list(deterministic_seeds),
        **SAFETY_FIELDS,
        **payload,
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def semantic_projection(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: semantic_projection(value)
            for key, value in sorted(payload.items())
            if key not in {"generated_at", "output_directory"}
        }
    if isinstance(payload, list):
        return [semantic_projection(value) for value in payload]
    return payload


def semantic_hash(payload: Any) -> str:
    return canonical_hash(semantic_projection(payload))


def build_semantic_hash_manifest(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    records: list[dict[str, str]] = []
    for path in sorted(root.glob("*.json")):
        if path.name == "semantic_hash_manifest.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        records.append(
            {
                "path": path.name,
                "sha256": sha256_file(path),
                "semantic_sha256": semantic_hash(payload),
            }
        )
    return {"artifacts": records, "manifest_semantic_sha256": canonical_hash(records)}
