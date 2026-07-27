from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ManifestEvidence:
    observed_manifest_identity: bool
    manifest_capture_ts: str
    manifest_contract_identity: str
    manifest_hash: str

