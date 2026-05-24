from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.runtime_snapshot_store import read_snapshot, read_snapshot_with_freshness
from core.top_opportunity_executable_truth import normalize_top_opportunity_payload


def read_snapshot_payload(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser()
    freshness = _read_dashboard_snapshot_freshness(target)
    if not target.exists():
        return {
            "state": "missing",
            "path": str(target),
            "errors": [f"missing:{target}"],
            "payload": {},
            **freshness,
        }
    try:
        envelope = read_snapshot(target)
    except Exception as exc:
        return {
            "state": "invalid",
            "path": str(target),
            "errors": [f"read_error:{type(exc).__name__}:{exc}"],
            "payload": {},
            **freshness,
        }
    if not isinstance(envelope, dict):
        return {
            "state": "invalid",
            "path": str(target),
            "errors": ["snapshot_envelope_not_object"],
            "payload": {},
            **freshness,
        }
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return {
            "state": "invalid",
            "path": str(target),
            "errors": ["snapshot_payload_not_object"],
            "payload": {},
            **freshness,
        }
    payload = _normalize_dashboard_snapshot_payload(payload)
    try:
        json.dumps(payload, default=str)
    except Exception as exc:
        return {
            "state": "invalid",
            "path": str(target),
            "errors": [f"payload_not_json_serializable:{type(exc).__name__}:{exc}"],
            "payload": {},
            **freshness,
        }
    return {
        "state": "ok",
        "path": str(target),
        "errors": [],
        "payload": payload,
        "generated_at": envelope.get("generated_at"),
        "producer": envelope.get("producer"),
        "schema_version": envelope.get("schema_version"),
        **freshness,
    }


def _normalize_dashboard_snapshot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not _looks_like_top_opportunity_payload(payload):
        return payload
    normalized, report = normalize_top_opportunity_payload(payload)
    out = dict(normalized)
    out["top_opportunity_truth_report"] = report.to_dict()
    return out


def _looks_like_top_opportunity_payload(payload: dict[str, Any]) -> bool:
    return bool(
        isinstance(payload, dict)
        and (
            "top_executable_opportunities" in payload
            or "top_advisory_opportunities" in payload
        )
    )


def _read_dashboard_snapshot_freshness(path: Path) -> dict[str, Any]:
    result = read_snapshot_with_freshness(path, artifact_name=path.name)
    freshness = result.get("freshness") if isinstance(result, dict) else None
    if not isinstance(freshness, dict):
        freshness = {}
    blockers = result.get("blockers") if isinstance(result, dict) else []
    if not isinstance(blockers, list):
        blockers = []
    return {
        "fresh": bool(result.get("fresh")) if isinstance(result, dict) else False,
        "freshness_status": str(freshness.get("status") or "unknown"),
        "freshness_age_seconds": freshness.get("age_seconds"),
        "freshness_timestamp_source": freshness.get("timestamp_source"),
        "freshness_blockers": list(blockers),
        "freshness": freshness,
    }
