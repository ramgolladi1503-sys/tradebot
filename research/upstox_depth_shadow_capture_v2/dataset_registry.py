from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEVELOPMENT = "DEVELOPMENT"
HOLDOUT_UNSEEN = "HOLDOUT_UNSEEN"
READY_CLASSIFICATION = "SHADOW_DEPTH_SESSION_READY_FOR_DEVELOPMENT"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def update_dataset_registry(
    output_root: Path,
    *,
    development_target: int = 60,
    holdout_target: int = 20,
) -> dict[str, Any]:
    if development_target <= 0 or holdout_target <= 0:
        raise ValueError("development_target and holdout_target must be positive")
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    registry_path = root / "dataset_registry.json"
    existing = _load_json(registry_path) if registry_path.exists() else {}

    assignments: dict[str, str] = {
        str(item["session_date"]): str(item["split"])
        for item in existing.get("assignments", [])
    }
    for session_date, split in assignments.items():
        if split not in {DEVELOPMENT, HOLDOUT_UNSEEN}:
            raise ValueError(f"unknown immutable split for {session_date}: {split}")

    ready_dates: list[str] = []
    unready_sessions: list[dict[str, str]] = []
    readiness_hashes: dict[str, str] = {}
    import hashlib

    for session_dir in sorted(root.iterdir()):
        if not session_dir.is_dir() or len(session_dir.name) != 8 or not session_dir.name.isdigit():
            continue
        readiness_path = session_dir / "readiness.json"
        if not readiness_path.exists():
            unready_sessions.append(
                {"session_date": session_dir.name, "classification": "READINESS_MISSING"}
            )
            continue
        payload = _load_json(readiness_path)
        classification = str(payload.get("classification") or "UNKNOWN")
        digest = hashlib.sha256(readiness_path.read_bytes()).hexdigest()
        readiness_hashes[session_dir.name] = digest
        if classification == READY_CLASSIFICATION:
            ready_dates.append(session_dir.name)
        else:
            unready_sessions.append(
                {"session_date": session_dir.name, "classification": classification}
            )

    ready_set = set(ready_dates)
    stale_assignments = sorted(set(assignments).difference(ready_set))
    if stale_assignments:
        raise ValueError(
            "previously assigned sessions no longer have a ready evidence file: "
            + ",".join(stale_assignments)
        )

    development_count = sum(split == DEVELOPMENT for split in assignments.values())
    holdout_count = sum(split == HOLDOUT_UNSEEN for split in assignments.values())
    for session_date in sorted(ready_dates):
        if session_date in assignments:
            continue
        if development_count < development_target:
            assignments[session_date] = DEVELOPMENT
            development_count += 1
        else:
            assignments[session_date] = HOLDOUT_UNSEEN
            holdout_count += 1

    if development_count < development_target:
        status = "DEVELOPMENT_ACQUISITION_IN_PROGRESS"
    elif holdout_count < holdout_target:
        status = "DEVELOPMENT_READY_HOLDOUT_ACQUISITION_IN_PROGRESS"
    else:
        status = "DATASET_ACQUISITION_COMPLETE_CANDIDATE_FREEZE_REQUIRED"

    ordered_assignments = [
        {
            "session_date": session_date,
            "split": assignments[session_date],
            "readiness_sha256": readiness_hashes[session_date],
        }
        for session_date in sorted(assignments)
    ]
    payload = {
        "campaign_id": "UPSTOX_DEPTH_SHADOW_CAPTURE_V2",
        "classification": status,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "development_target": development_target,
        "holdout_target": holdout_target,
        "development_ready_sessions": development_count,
        "holdout_unseen_ready_sessions": holdout_count,
        "development_complete": development_count >= development_target,
        "holdout_complete": holdout_count >= holdout_target,
        "assignments": ordered_assignments,
        "unready_sessions": sorted(unready_sessions, key=lambda item: item["session_date"]),
        "assignment_mutation_allowed": False,
        "holdout_use_for_discovery_allowed": False,
        "holdout_outcome_access_allowed": False,
        "candidate_equation_frozen": False,
        "strategy_created": False,
        "edge_claim_allowed": False,
        "execution_allowed": False,
    }
    _atomic_json(registry_path, payload)
    return payload
