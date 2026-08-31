"""Session-bound metadata manager for isolated PR validation sidecars."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.live_sidecar_contract import load_sidecar_registry, sidecar_health


def write_sidecar_health(*, registry_path: str | Path, output_path: str | Path,
                         main_session_id: str, source_sha: str) -> dict[str, Any]:
    specs = load_sidecar_registry(registry_path)
    health = []
    for spec in specs:
        row = sidecar_health(spec, main_session_id=main_session_id)
        row.update({"MAIN_SOURCE_SHA": source_sha, "STATUS": "PENDING"})
        health.append(row)
    payload = {
        "schema_version": 1,
        "main_session_id": main_session_id,
        "main_source_sha": source_sha,
        "sidecar_count": len(health),
        "sidecars": health,
        "canonical_feed_owner_count": 1,
        "failure_isolation": True,
        "pr_sidecars_isolated": True,
        "broker_write_authority": False,
        "order_authority": False,
        "live_db_writes": 0,
        "broker_order_calls": 0,
        "verdict": "PENDING",
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return payload
