"""Revival Candidate Registry & Queue Isolation Specification.

Governs Top-20 revival candidates, partitioning them into:
  - Queue 1: Reconciled Frozen Prospective Shadow (Strictly no retuning / search)
  - Queue 2: Research Repair (Multi-leg options, orthogonalization, basis translation)
  - Queue 3: 2026 Anomaly Observation Ledger (Fixed criteria, zero optimization compute)

Enforces fail-closed candidate reconciliation and prevents Queue 2/3 from
contaminating Queue 1 prospective streams.
"""

from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Literal

CandidateStatus = Literal[
    "RECONCILED_FOR_PROSPECTIVE_SHADOW",
    "BLOCKED_RECONCILIATION_REQUIRED",
    "BLOCKED_AUTHORITY_CONFLICT",
    "BLOCKED_DATA_IDENTITY",
]

QueueType = Literal["QUEUE_1_SHADOW", "QUEUE_2_REPAIR", "QUEUE_3_ANOMALY"]


@dataclass(frozen=True)
class CandidateFreezeManifest:
    strategy_id: str
    candidate_version: str
    reconciliation_status: CandidateStatus
    source_artifact_paths: List[str]
    source_artifact_sha256s: Dict[str, str]
    source_git_sha: str
    data_source_ids: List[str]
    data_source_sha256s: Dict[str, str]
    timezone: str
    signal_definition: str
    entry_definition: str
    exit_definition: str
    direction_definition: str
    thresholds: Dict[str, float]
    filters: List[str]
    boundary_semantics: str
    missing_data_policy: str
    instrument_semantics: str
    cost_semantics: str
    historical_periods: Dict[str, str]
    prospective_start_boundary: str
    queue: QueueType
    reconciliation_blocker_reason: Optional[str] = None

    def canonical_json(self) -> str:
        """Deterministic canonical JSON serialization."""
        d = {
            "strategy_id": self.strategy_id,
            "candidate_version": self.candidate_version,
            "reconciliation_status": self.reconciliation_status,
            "source_artifact_paths": sorted(self.source_artifact_paths),
            "source_artifact_sha256s": {k: self.source_artifact_sha256s[k] for k in sorted(self.source_artifact_sha256s)},
            "source_git_sha": self.source_git_sha,
            "data_source_ids": sorted(self.data_source_ids),
            "data_source_sha256s": {k: self.data_source_sha256s[k] for k in sorted(self.data_source_sha256s)},
            "timezone": self.timezone,
            "signal_definition": self.signal_definition,
            "entry_definition": self.entry_definition,
            "exit_definition": self.exit_definition,
            "direction_definition": self.direction_definition,
            "thresholds": {k: self.thresholds[k] for k in sorted(self.thresholds)},
            "filters": sorted(self.filters),
            "boundary_semantics": self.boundary_semantics,
            "missing_data_policy": self.missing_data_policy,
            "instrument_semantics": self.instrument_semantics,
            "cost_semantics": self.cost_semantics,
            "historical_periods": {k: self.historical_periods[k] for k in sorted(self.historical_periods)},
            "prospective_start_boundary": self.prospective_start_boundary,
            "queue": self.queue,
            "reconciliation_blocker_reason": self.reconciliation_blocker_reason,
        }
        return json.dumps(d, sort_keys=True, separators=(",", ":"))

    def compute_spec_hash(self) -> str:
        """SHA-256 hash of canonical specification payload."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


class RevivalRegistry:
    """Registry maintaining frozen manifests and queue partition invariants."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path("/Users/madhuram/tradebot")
        self._manifests: Dict[str, CandidateFreezeManifest] = {}
        self._load_authoritative_manifests()

    def _load_authoritative_manifests(self) -> None:
        manifest_path = self.repo_root / "output/revival_candidate_freeze_manifests_20260922.json"
        if not manifest_path.exists():
            return

        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for cid, cdata in data.get("candidates", {}).items():
            # Assign appropriate queue
            if cid in ("CAND_01_SESSION_DIR_OVERNIGHT", "CAND_02_GAP_DIR_CONFLUENCE_A",
                       "CAND_03_DAY_NIGHT_MOMENTUM", "CAND_04_LOW_GAP_LOW_PRIOR_RET",
                       "CAND_05_DAY_NIGHT_OI_CONFIRM", "CAND_06_GAP_CONFLUENCE_RANGE_EXP_B"):
                queue = "QUEUE_1_SHADOW"
            else:
                queue = "QUEUE_3_ANOMALY"

            manifest = CandidateFreezeManifest(
                strategy_id=cdata["strategy_id"],
                candidate_version=cdata.get("candidate_version", "1.0.0"),
                reconciliation_status=cdata.get("reconciliation_status", "BLOCKED_RECONCILIATION_REQUIRED"),
                source_artifact_paths=cdata.get("source_artifact_paths", []),
                source_artifact_sha256s=cdata.get("source_artifact_sha256s", {}),
                source_git_sha=cdata.get("source_git_sha", ""),
                data_source_ids=cdata.get("data_source_ids", []),
                data_source_sha256s=cdata.get("data_source_sha256s", {}),
                timezone=cdata.get("timezone", "Asia/Kolkata"),
                signal_definition=cdata.get("signal_definition", ""),
                entry_definition=cdata.get("entry_definition", ""),
                exit_definition=cdata.get("exit_definition", ""),
                direction_definition=cdata.get("direction_definition", ""),
                thresholds=cdata.get("thresholds", {}),
                filters=cdata.get("filters", []),
                boundary_semantics=cdata.get("boundary_semantics", ""),
                missing_data_policy=cdata.get("missing_data_policy", ""),
                instrument_semantics=cdata.get("instrument_semantics", ""),
                cost_semantics=cdata.get("cost_semantics", ""),
                historical_periods=cdata.get("historical_periods", {}),
                prospective_start_boundary=cdata.get("prospective_start_boundary", ""),
                queue=queue,
                reconciliation_blocker_reason=cdata.get("reconciliation_blocker_reason"),
            )
            self._manifests[cid] = manifest

    def get_manifest(self, strategy_id: str) -> Optional[CandidateFreezeManifest]:
        return self._manifests.get(strategy_id)

    def verify_source_artifacts(self, strategy_id: str) -> bool:
        """Verify that on-disk source artifacts match their frozen sha256 hashes."""
        manifest = self.get_manifest(strategy_id)
        if not manifest:
            return False
        for path_str, expected_hash in manifest.source_artifact_sha256s.items():
            full_path = self.repo_root / path_str
            if not full_path.exists():
                return False
            with open(full_path, "rb") as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest()
            if actual_hash != expected_hash:
                return False
        return True

    def get_reconciled_queue_1_candidates(self) -> List[CandidateFreezeManifest]:
        """Return only Queue 1 candidates that have achieved RECONCILED_FOR_PROSPECTIVE_SHADOW."""
        reconciled = []
        for m in self._manifests.values():
            if m.queue == "QUEUE_1_SHADOW" and m.reconciliation_status == "RECONCILED_FOR_PROSPECTIVE_SHADOW":
                # Must also verify artifact hashes match on disk
                if self.verify_source_artifacts(m.strategy_id):
                    reconciled.append(m)
        return reconciled
