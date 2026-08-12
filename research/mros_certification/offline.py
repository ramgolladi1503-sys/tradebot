"""Exact-SHA-bound offline evidence validation.

This module validates evidence declarations only.  It does not run CI, invoke
brokers, promote models, or infer live/prospective readiness.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CertificationResult:
    candidate_sha: str
    task_ids: tuple[str, ...]
    status: str
    independent_verification: str
    ci: str
    safety: Mapping[str, bool]


def validate_offline_manifest(
    manifest: Mapping[str, object],
    *,
    candidate_sha: str,
    required_tasks: Sequence[str],
) -> CertificationResult:
    """Validate a manifest without converting declarations into certification."""
    _require_sha(candidate_sha)
    if manifest.get("candidate_sha") != candidate_sha:
        raise ValueError("EVIDENCE_CANDIDATE_SHA_MISMATCH")
    task_ids = tuple(manifest.get("task_ids", ()))
    if task_ids != tuple(required_tasks) or len(set(task_ids)) != len(task_ids):
        raise ValueError("EVIDENCE_TASK_BINDING_INVALID")
    if manifest.get("live_or_prospective_claimed", False):
        raise ValueError("OFFLINE_MANIFEST_CANNOT_CLAIM_LIVE")
    safety = manifest.get("safety")
    expected = {
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
    }
    if safety != expected:
        raise ValueError("SAFETY_BOUNDARY_INVALID")
    if manifest.get("status") != "OFFLINE_EVIDENCE_VALID":
        raise ValueError("OFFLINE_EVIDENCE_NOT_VALID")
    for key in ("focused", "adversarial", "integration"):
        evidence = manifest.get(key)
        if not isinstance(evidence, Mapping) or evidence.get("status") != "PASS" or evidence.get("candidate_sha") != candidate_sha:
            raise ValueError(f"{key.upper()}_EVIDENCE_INVALID")
    return CertificationResult(
        candidate_sha=candidate_sha,
        task_ids=task_ids,
        status="OFFLINE_EVIDENCE_VALID_PENDING_INDEPENDENT_REVIEW",
        independent_verification="PENDING",
        ci="PENDING",
        safety=expected,
    )


def manifest_sha256(manifest: Mapping[str, object]) -> str:
    """Return a deterministic digest for an immutable evidence declaration."""
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _require_sha(value: object) -> None:
    if not isinstance(value, str) or len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError("CANDIDATE_SHA_REQUIRED")
