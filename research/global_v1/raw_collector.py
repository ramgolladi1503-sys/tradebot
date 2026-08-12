"""Offline raw global artifact collector; no network or broker authority."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class RawArtifact:
    source_name: str
    provider: str
    path: str
    sha256: str
    payload: Mapping[str, object]


def collect_raw_artifact(path: str | Path, *, source_name: str, provider: str, expected_sha256: str) -> RawArtifact:
    file_path = Path(path)
    raw = file_path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise ValueError("GLOBAL_RAW_SHA_MISMATCH")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("GLOBAL_RAW_MAPPING_REQUIRED")
    if not source_name or not provider:
        raise ValueError("GLOBAL_RAW_PROVENANCE_REQUIRED")
    return RawArtifact(source_name, provider, str(file_path), actual, payload)
