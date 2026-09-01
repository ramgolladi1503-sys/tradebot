"""Append-only advisory sink shared by canonical consumers and sidecars."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


REQUIRED_FIELDS = frozenset({"candidate_id", "strategy_id", "timestamp", "source_sha", "spec_sha", "execution_status"})


def normalize_advisory(row: Mapping[str, Any], *, session_id: str) -> dict[str, Any]:
    payload = dict(row)
    missing = sorted(REQUIRED_FIELDS - payload.keys())
    if missing:
        raise ValueError("advisory_missing_fields:" + ",".join(missing))
    if payload.get("execution_status") != "advisory_only":
        raise ValueError("advisory_execution_status_not_advisory_only")
    payload.update({
        "session_id": session_id,
        "read_only": True,
        "is_order_action": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_execution_authorized": False,
        "orders_placed": 0,
        "orders_modified": 0,
        "orders_cancelled": 0,
    })
    return payload


def append_advisory(path: str | Path, row: Mapping[str, Any], *, session_id: str) -> str:
    payload = normalize_advisory(row, session_id=session_id)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    payload["advisory_sha256"] = digest
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    identity = tuple(payload.get(key) for key in ("session_id", "strategy_id", "symbol", "decision_timestamp"))
    if destination.exists():
        for line in destination.read_text(encoding="utf-8").splitlines():
            try:
                prior = json.loads(line)
            except json.JSONDecodeError:
                continue
            if tuple(prior.get(key) for key in ("session_id", "strategy_id", "symbol", "decision_timestamp")) == identity:
                return str(prior.get("advisory_sha256") or digest)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return digest
