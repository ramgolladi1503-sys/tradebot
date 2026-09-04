"""Read-only runtime adapter for MARKET_STATE_ENGINE_V1.

The adapter accepts per-index feature snapshots from an authoritative upstream
producer and atomically publishes one current artifact plus an append-only JSONL
ledger. It performs no market-data fetching and has no execution authority.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.market_state_engine_v1 import MarketStateDecision, classify_cross_index_consensus, classify_market_state

ARTIFACT_NAME = "market_state_engine_v1.json"
LEDGER_NAME = "market_state_engine_v1.jsonl"


def evaluate_live_market_state(
    snapshots: Mapping[str, Mapping[str, Any]],
    *,
    previous_zones: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    prior = dict(previous_zones or {})
    decisions: dict[str, MarketStateDecision] = {}
    for symbol in ("NIFTY", "BANKNIFTY", "SENSEX"):
        snapshot = snapshots.get(symbol)
        decisions[symbol] = classify_market_state(snapshot, symbol=symbol, previous_zone=prior.get(symbol))
    consensus = classify_cross_index_consensus(decisions)
    healthy = all(not decision.blockers for decision in decisions.values())
    return {
        "schema_version": 1,
        "source": "live_market_state_runtime_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "PASS" if healthy else "BLOCKED",
        "regime_healthy": healthy,
        "indices": {symbol: decision.to_payload() for symbol, decision in decisions.items()},
        "cross_index": consensus,
        "read_only": True,
        "execution_capable": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_execution_authorized": False,
        "broker_order_calls": 0,
    }


def publish_live_market_state(
    output_root: str | Path,
    *,
    snapshots: Mapping[str, Mapping[str, Any]],
    session_id: str,
    source_sha: str,
    previous_zones: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not session_id or len(str(source_sha)) != 40:
        raise ValueError("market_state_runtime_identity_invalid")
    payload = evaluate_live_market_state(snapshots, previous_zones=previous_zones)
    payload["session_id"] = session_id
    payload["source_sha"] = source_sha

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    artifact = root / ARTIFACT_NAME
    temporary = artifact.with_name(artifact.name + ".tmp")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(artifact)
    with (root / LEDGER_NAME).open("a", encoding="utf-8") as handle:
        handle.write(encoded)
    return payload


def previous_zones_from_payload(payload: Mapping[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    indices = dict((payload or {}).get("indices") or {})
    for symbol, state in indices.items():
        zone = str(dict(state or {}).get("zone") or "").upper()
        if zone:
            out[str(symbol).upper()] = zone
    return out


__all__ = ["evaluate_live_market_state", "publish_live_market_state", "previous_zones_from_payload"]
