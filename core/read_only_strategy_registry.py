"""Canonical strategy declarations for the read-only live pipeline.

The registry is deliberately declarative.  An entry is not considered to have
run merely because it appears here; runtime evidence must record an actual
invocation and its output identity.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


CANONICAL_STRATEGIES = (
    {
        "strategy_id": "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1",
        "enabled": True,
        "inputs": ("09:15_10:00_underlying_return", "15:14_fresh_observation"),
        "regime_dependencies": (),
        "candidate_type": "causal_advisory",
        "mode": "advisory_only",
    },
)

SUPERSEDED_STRATEGIES = ({"strategy_id": "CAS_SW_RUNTIME_V2_1514", "status": "SUPERSEDED", "enabled": False, "superseded_by": "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1"},)


def _spec_sha(spec: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(spec), sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_strategy_registry(*, session_id: str, source_sha: str) -> dict[str, Any]:
    if not session_id or len(source_sha) != 40:
        raise ValueError("strategy_registry_identity_missing")
    entries = []
    for declaration in CANONICAL_STRATEGIES:
        spec = dict(declaration)
        spec["inputs"] = list(spec["inputs"])
        spec["regime_dependencies"] = list(spec["regime_dependencies"])
        spec_sha = _spec_sha(spec)
        entries.append({
            **spec,
            "spec_sha": spec_sha,
            "session_id": session_id,
            "source_sha": source_sha,
            "runtime_status": "PENDING",
            "invocation_count": 0,
            "candidate_count": 0,
            "execution_status": "advisory_only",
            "read_only": True,
            "broker_write_authority": False,
            "order_authority": False,
        })
    return {
        "schema_version": 1,
        "session_id": session_id,
        "source_sha": source_sha,
        "strategies": entries,
        "verdict": "PENDING",
        "read_only": True,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_execution_authorized": False,
    }


def write_strategy_registry(path: str | Path, *, session_id: str, source_sha: str) -> dict[str, Any]:
    destination = Path(path)
    if destination.exists():
        raise FileExistsError("strategy_registry_already_exists")
    payload = build_strategy_registry(session_id=session_id, source_sha=source_sha)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return payload
