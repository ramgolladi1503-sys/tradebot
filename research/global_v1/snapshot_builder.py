"""Deterministic causal Global Context V1 target-session snapshot builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
from typing import Mapping

from core.global_context_evidence_contract import GlobalObservation, build_causal_snapshot


REQUIRED_SOURCES = ("DXY", "SPX", "NASDAQ", "VIX")


@dataclass(frozen=True)
class SnapshotPolicy:
    max_age: timedelta
    required_sources: tuple[str, ...] = REQUIRED_SOURCES


def build_target_session_snapshot(
    observations: Mapping[str, GlobalObservation],
    *,
    cutoff: datetime,
    policy: SnapshotPolicy,
) -> dict[str, object]:
    """Build an immutable snapshot; missing inputs remain explicit and block sealing."""

    missing = tuple(source for source in policy.required_sources if source not in observations)
    if missing:
        return {
            "status": "BLOCKED_DATA",
            "missing_sources": missing,
            "cutoff": cutoff.isoformat(),
            "snapshot_sha256": _hash({"status": "BLOCKED_DATA", "missing_sources": missing, "cutoff": cutoff.isoformat()}),
        }
    for name in policy.required_sources:
        observation = observations[name]
        observation.validate(cutoff=cutoff)
        if cutoff - observation.observed_at > policy.max_age:
            raise ValueError(f"GLOBAL_STALE_OBSERVATION:{name}")
    snapshot = build_causal_snapshot(observations, cutoff=cutoff)
    return {"status": "READY", "missing_sources": (), "policy_max_age_seconds": policy.max_age.total_seconds(), **snapshot}


def verify_snapshot(snapshot: Mapping[str, object]) -> None:
    claimed = snapshot.get("snapshot_sha256")
    if not isinstance(claimed, str):
        raise ValueError("GLOBAL_SNAPSHOT_SHA_MISSING")
    payload = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
    # READY snapshots use the underlying causal payload hash; blocked snapshots
    # use the full deterministic blocker payload hash.
    if snapshot.get("status") == "READY":
        payload = {"cutoff": snapshot["cutoff"], "observations": snapshot["observations"]}
    if _hash(payload) != claimed:
        raise ValueError("GLOBAL_SNAPSHOT_TAMPERED")


def _hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
