"""Independent validation of one canonical read-only session artifact set."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FALSE_AUTHORITY = (
    "broker_write_authority", "order_authority", "paper_authorized",
    "live_execution_authorized",
)


def _load(root: Path, name: str) -> dict[str, Any]:
    path = root / name
    if not path.is_file():
        raise ValueError(f"validation_artifact_missing:{name}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"validation_artifact_not_object:{name}")
    return payload


def validate_session_artifacts(*, runtime_root: str | Path, source_sha: str,
                               require_e2e: bool = False) -> dict[str, Any]:
    root = Path(runtime_root)
    manifest = _load(root, "SESSION_MANIFEST.json")
    consumers = _load(root, "CONSUMERS.json")
    strategies = _load(root, "STRATEGY_REGISTRY.json")
    sidecars = _load(root, "SIDECAR_HEALTH.json")
    exit_gate = _load(root, "session_exit_gate.json")
    failures: list[str] = []
    if manifest.get("source_sha") != source_sha or manifest.get("pipeline_sha") != source_sha:
        failures.append("source_identity_mismatch")
    for name, payload in (("manifest", manifest), ("consumers", consumers), ("strategies", strategies), ("sidecars", sidecars), ("exit_gate", exit_gate)):
        for field in FALSE_AUTHORITY:
            if payload.get(field) is not False:
                failures.append(f"{name}_authority_not_false:{field}")
    if consumers.get("execution_capable") is not False:
        failures.append("consumer_execution_capable")
    if sidecars.get("canonical_feed_owner_count") != 1 or sidecars.get("pr_sidecars_isolated") is not True:
        failures.append("sidecar_isolation_contract_missing")
    if sidecars.get("broker_order_calls") != 0 or sidecars.get("live_db_writes") != 0:
        failures.append("sidecar_mutation_counts_nonzero")
    if exit_gate.get("broker_order_calls") != 0:
        failures.append("exit_gate_broker_order_calls_nonzero")
    e2e = exit_gate.get("live_observation_e2e_ready") is True and exit_gate.get("verdict") == "PASS"
    if require_e2e and not e2e:
        failures.append("current_session_e2e_not_proven")
    verdict = "PROMOTION_ELIGIBLE" if not failures and e2e else "BLOCKED"
    return {
        "schema_version": 1,
        "verdict": verdict,
        "promotion_eligible": verdict == "PROMOTION_ELIGIBLE",
        "e2e_proven": e2e,
        "failures": failures,
        "source_sha": source_sha,
        "read_only": True,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_execution_authorized": False,
    }

