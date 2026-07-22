"""Supervisor-integrated public entry point for governed strategy research."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from core.governed_strategy_research import (
    ALLOWED_AGENTS,
    AgentRole,
    FORBIDDEN_PATH_PREFIXES,
    GovernedResearchStore as _BaseGovernedResearchStore,
    MANDATORY_GATES,
    ResearchError,
    ResearchState,
    ResearchStatus,
    SAFETY_ASSERTIONS,
    _load_json_object,
    _safe_relative_path,
    _sha256_file,
    build_validation_payload,
)


def _supervisor_manifest_hash_is_valid(payload: Mapping[str, Any]) -> bool:
    expected = str(payload.get("manifest_sha256") or "").strip()
    body = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    encoded = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return bool(expected) and expected == hashlib.sha256(encoded).hexdigest()


def _load_pinned_manifest(
    root: Path,
    relative_path: object,
    expected_file_sha256: object,
    *,
    label: str,
) -> tuple[str, dict[str, Any]]:
    relative = _safe_relative_path(relative_path)
    path = (root / relative).resolve()
    if root not in path.parents or not path.is_file():
        raise ResearchError(f"{label}_not_found")
    expected = str(expected_file_sha256 or "").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ResearchError(f"{label}_file_sha256_required")
    if _sha256_file(path) != expected:
        raise ResearchError(f"{label}_file_hash_mismatch")
    payload = _load_json_object(path, label=label)
    if not _supervisor_manifest_hash_is_valid(payload):
        raise ResearchError(f"{label}_internal_hash_invalid")
    return relative, payload


class GovernedResearchStore(_BaseGovernedResearchStore):
    """Public store that requires valid worktree-supervisor manifests."""

    def record_implementation(
        self,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        manifest = self._manifest()
        if manifest["state"] != ResearchState.HYPOTHESIS_FROZEN.value:
            return super().record_implementation(evidence)
        _, supervisor = _load_pinned_manifest(
            self.root,
            evidence.get("supervisor_manifest"),
            evidence.get("supervisor_manifest_file_sha256"),
            label="supervisor_manifest",
        )
        branch = str(evidence.get("branch") or "").strip()
        if not branch or branch in {"main", "master"}:
            raise ResearchError("isolated_implementation_branch_required")
        supervisor_branch = str(supervisor.get("branch") or "").strip()
        if supervisor_branch and supervisor_branch != branch:
            raise ResearchError("supervisor_manifest_branch_mismatch")
        artifacts = evidence.get("artifacts")
        if (
            not isinstance(artifacts, Sequence)
            or isinstance(artifacts, (str, bytes))
            or not artifacts
        ):
            raise ResearchError("implementation_artifacts_required")
        for artifact in artifacts:
            _safe_relative_path(artifact)
        return super().record_implementation(evidence)

    def record_review(self, evidence: Mapping[str, Any]) -> dict[str, Any]:
        manifest = self._manifest()
        if manifest["state"] != ResearchState.IMPLEMENTED.value:
            return super().record_review(evidence)
        _, supervisor_review = _load_pinned_manifest(
            self.root,
            evidence.get("supervisor_review_manifest"),
            evidence.get("supervisor_review_manifest_file_sha256"),
            label="supervisor_review_manifest",
        )
        if supervisor_review.get("blockers"):
            raise ResearchError("supervisor_review_manifest_has_blockers")
        return super().record_review(evidence)


__all__ = [
    "ALLOWED_AGENTS",
    "AgentRole",
    "FORBIDDEN_PATH_PREFIXES",
    "GovernedResearchStore",
    "MANDATORY_GATES",
    "ResearchError",
    "ResearchState",
    "ResearchStatus",
    "SAFETY_ASSERTIONS",
    "build_validation_payload",
]
