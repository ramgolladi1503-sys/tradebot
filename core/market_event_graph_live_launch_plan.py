"""Immutable launch-plan contract for governed live breadth observation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.market_event_graph_live_observation_registry import (
    BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET,
    build_observation_subscription_merge,
)

SCHEMA_VERSION = 1
SEMANTIC_SCHEMA_VERSION = 1
PASS_STATIC_LIVE_SOURCE_PREFLIGHT = "PASS_STATIC_LIVE_SOURCE_PREFLIGHT"
PASS_LIVE_SOURCE_PRESESSION_READINESS = "PASS_LIVE_SOURCE_PRESESSION_READINESS"
BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN = "BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN"
BLOCKED_BY_LAUNCH_PLAN_IDENTITY = "BLOCKED_BY_LAUNCH_PLAN_IDENTITY"
BLOCKED_BY_FROZEN_LAUNCH_PLAN = "BLOCKED_BY_FROZEN_LAUNCH_PLAN"


def _tokens(values: Sequence[int]) -> list[int]:
    return list(dict.fromkeys(int(value) for value in values if int(value) > 0))


def _sha(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def _stable_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()


def _semantic_resolution(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Keep selection-driving resolver output, excluding volatile quote values."""
    fields = (
        "symbol", "exchange", "expiry", "index_token", "step", "strikes_around",
        "option_strikes_selected", "tokens", "option_count", "resolved_count",
        "resolved_option_count", "final_count", "final_option_count", "option_min_required",
        "option_coverage_status", "option_coverage_reason", "index_token_source",
    )
    result = []
    for row in rows:
        result.append({key: _json_safe(row[key]) for key in fields if key in row})
    return sorted(result, key=lambda row: (str(row.get("exchange", "")), str(row.get("symbol", ""))))


def resolver_snapshot(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Capture the time-sensitive inputs used by production token resolution."""
    return {
        "schema_version": 1,
        "master_sha256": str(plan.get("master_sha256") or ""),
        "universe_sha256": str(plan.get("universe_sha256") or ""),
        "production_resolution": _json_safe(plan.get("production_resolution") or []),
        "production_tokens": _tokens(plan.get("production_tokens") or []),
    }


def canonicalize_launch_plan(plan: Mapping[str, Any], resolver_snapshot_hash: str = "") -> dict[str, Any]:
    """Build the documented semantic projection used for launch approval."""
    instruments = [{"instrument_token": int(token)} for token in _tokens(plan.get("final_union_tokens") or [])]
    instruments.sort(key=lambda row: row["instrument_token"])
    projection = {
        "semantic_schema_version": SEMANTIC_SCHEMA_VERSION,
        "session_date": str(plan.get("session_date") or ""),
        "observation_tokens": _tokens(plan.get("observation_tokens") or []),
        "final_union_tokens": _tokens(plan.get("final_union_tokens") or []),
        "instruments": instruments,
        "configured_budget": int(plan.get("configured_budget") or 0),
        "production_resolution": _semantic_resolution(plan.get("production_resolution") or []),
        "master_sha256": str(plan.get("master_sha256") or ""),
        "universe_sha256": str(plan.get("universe_sha256") or ""),
        "configuration_fingerprint": str(plan.get("configuration_fingerprint") or ""),
        "read_only": bool(plan.get("read_only")),
        "is_order_action": bool(plan.get("is_order_action")),
        "allowed_for_live_execution": bool(plan.get("allowed_for_live_execution")),
        "resolver_snapshot_sha256": str(resolver_snapshot_hash or ""),
    }
    for key in ("subscription_modes", "interval_seconds", "retry_bound", "campaign_id", "provider", "evidence_root"):
        if key in plan:
            projection[key] = _json_safe(plan[key])
    return projection


def semantic_sha256(plan: Mapping[str, Any], resolver_snapshot_hash: str = "") -> str:
    projection = canonicalize_launch_plan(plan, resolver_snapshot_hash)
    # The snapshot reference is provenance, not launch semantics. A quote-only
    # snapshot change must be visible in resolver identity without changing the
    # semantic plan when selected instruments and controls remain unchanged.
    projection.pop("resolver_snapshot_sha256", None)
    return _stable_sha(projection)


def build_launch_plan(
    *,
    session_date: str,
    production_tokens: Sequence[int],
    production_resolution: Sequence[Mapping[str, Any]],
    sticky_tokens: Sequence[int],
    observation_tokens: Sequence[int],
    budget: int,
    master_sha256: str,
    universe_sha256: str,
    configuration: Mapping[str, Any],
    broker_metadata_called: bool,
    resolver_snapshot_sha256: str = "",
) -> dict[str, Any]:
    production = _tokens(production_tokens)
    observation = _tokens(observation_tokens)
    sticky = _tokens(sticky_tokens)
    resolution = [_json_safe(dict(row)) for row in production_resolution]
    underlying = _tokens([row.get("index_token") for row in resolution if row.get("index_token")])
    option_tokens = [token for token in production if token not in set(underlying) and token not in set(sticky)]
    merge = build_observation_subscription_merge(
        production_tokens=production,
        observation_tokens=observation,
        budget=int(budget),
    )
    config_fingerprint = _sha(dict(configuration))
    basis = {
        "schema_version": SCHEMA_VERSION,
        "session_date": str(session_date),
        "production_tokens": production,
        "production_underlying_tokens": underlying,
        "production_option_tokens": option_tokens,
        "production_sticky_tokens": sticky,
        "observation_tokens": observation,
        "overlap_tokens": sorted(set(production) & set(observation)),
        "observation_exclusive_tokens": sorted(set(observation) - set(production)),
        "final_union_tokens": list(merge["tokens"]) if merge["ok"] else [],
        "configured_budget": int(budget),
        "missing_observation_tokens": list(merge["missing_or_pruned_observation_tokens"]),
        "production_resolution": resolution,
        "master_sha256": str(master_sha256),
        "universe_sha256": str(universe_sha256),
        "configuration_fingerprint": config_fingerprint,
        "broker_metadata_called": bool(broker_metadata_called),
    }
    plan_sha = _sha(basis)
    snapshot = {
        "schema_version": 1,
        "master_sha256": str(master_sha256),
        "universe_sha256": str(universe_sha256),
        "production_resolution": resolution,
        "production_tokens": production,
    }
    snapshot_sha = str(resolver_snapshot_sha256 or _stable_sha(snapshot))
    semantic = canonicalize_launch_plan({**basis, "session_date": session_date, "read_only": True, "is_order_action": False, "allowed_for_live_execution": False}, snapshot_sha)
    ok = bool(merge["ok"] and len(observation) == 51 and len(basis["final_union_tokens"]) == len(set(production) | set(observation)))
    return {
        **basis,
        "ok": ok,
        "verdict": PASS_LIVE_SOURCE_PRESESSION_READINESS if ok else merge["reason"],
        "production_token_count": len(production),
        "production_underlying_count": len(underlying),
        "production_option_count": len(option_tokens),
        "production_sticky_count": len(sticky),
        "observation_token_count": len(observation),
        "overlap_count": len(basis["overlap_tokens"]),
        "observation_exclusive_count": len(basis["observation_exclusive_tokens"]),
        "final_union_count": len(basis["final_union_tokens"]),
        "launch_plan_sha256": plan_sha,
        "resolver_snapshot_sha256": snapshot_sha,
        "canonical_semantic_launch_plan": semantic,
        "semantic_launch_plan_sha256": semantic_sha256(
            {**basis, "session_date": session_date, "read_only": True, "is_order_action": False, "allowed_for_live_execution": False},
            snapshot_sha,
        ),
        "read_only": True,
        "is_order_action": False,
        "allowed_for_live_execution": False,
    }


def write_launch_plan(path: Path, plan: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(_json_safe(dict(plan)), handle, sort_keys=True, indent=2)
        handle.write("\n")


def load_launch_plan(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(BLOCKED_BY_LAUNCH_PLAN_IDENTITY)
    claimed = str(raw.get("launch_plan_sha256") or "")
    basis = {
        key: raw[key]
        for key in (
            "schema_version", "session_date", "production_tokens", "production_underlying_tokens",
            "production_option_tokens", "production_sticky_tokens", "observation_tokens", "overlap_tokens",
            "observation_exclusive_tokens", "final_union_tokens", "configured_budget",
            "missing_observation_tokens", "production_resolution", "master_sha256", "universe_sha256",
            "configuration_fingerprint", "broker_metadata_called",
        )
        if key in raw
    }
    if claimed != _sha(basis) or not bool(raw.get("ok")):
        raise ValueError(BLOCKED_BY_LAUNCH_PLAN_IDENTITY)
    if len(_tokens(raw.get("observation_tokens") or [])) != 51:
        raise ValueError(BLOCKED_BY_LAUNCH_PLAN_IDENTITY)
    return raw


def verify_frozen_launch_plan(
    path: Path,
    *,
    expected_semantic_sha256: str,
    expected_resolver_snapshot_sha256: str,
    session_date: str,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    """Fail closed before any feed object is constructed."""
    frozen_root = path.resolve().parent
    if not (frozen_root / "FROZEN").is_file():
        raise ValueError(f"{BLOCKED_BY_FROZEN_LAUNCH_PLAN}:FROZEN_MARKER_MISSING")
    plan = load_launch_plan(path)
    if str(plan.get("session_date")) != str(session_date):
        raise ValueError(f"{BLOCKED_BY_FROZEN_LAUNCH_PLAN}:SESSION_DATE_MISMATCH")
    if campaign_id is not None and str(plan.get("campaign_id") or "") != str(campaign_id):
        raise ValueError(f"{BLOCKED_BY_FROZEN_LAUNCH_PLAN}:CAMPAIGN_MISMATCH")
    snapshot_path = frozen_root / "resolver_snapshot.json"
    if not snapshot_path.is_file():
        snapshot_path = frozen_root / "resolver_snapshot" / "resolver_inputs.json"
    if not snapshot_path.is_file():
        raise ValueError(f"{BLOCKED_BY_FROZEN_LAUNCH_PLAN}:RESOLVER_SNAPSHOT_MISSING")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot_hash = _stable_sha(snapshot)
    if snapshot_hash != str(expected_resolver_snapshot_sha256):
        raise ValueError(f"{BLOCKED_BY_FROZEN_LAUNCH_PLAN}:RESOLVER_SNAPSHOT_MISMATCH")
    actual_semantic = semantic_sha256(plan, snapshot_hash)
    if actual_semantic != str(expected_semantic_sha256):
        raise ValueError(f"{BLOCKED_BY_FROZEN_LAUNCH_PLAN}:SEMANTIC_HASH_MISMATCH")
    tokens = _tokens(plan.get("final_union_tokens") or [])
    if len(tokens) != 123 or len(tokens) != len(set(tokens)) or len(_tokens(plan.get("observation_tokens") or [])) != 51:
        raise ValueError(f"{BLOCKED_BY_FROZEN_LAUNCH_PLAN}:TOKEN_CONTRACT_MISMATCH")
    if int(plan.get("configured_budget") or 0) > 150 or plan.get("read_only") is not True or plan.get("allowed_for_live_execution") is not False:
        raise ValueError(f"{BLOCKED_BY_FROZEN_LAUNCH_PLAN}:AUTHORITY_OR_BUDGET_MISMATCH")
    return {"ok": True, "semantic_sha256": actual_semantic, "resolver_snapshot_sha256": snapshot_hash, "token_count": len(tokens)}


__all__ = [
    "BLOCKED_BY_LAUNCH_PLAN_IDENTITY",
    "BLOCKED_BY_FROZEN_LAUNCH_PLAN",
    "BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN",
    "PASS_STATIC_LIVE_SOURCE_PREFLIGHT",
    "PASS_LIVE_SOURCE_PRESESSION_READINESS",
    "build_launch_plan",
    "canonicalize_launch_plan",
    "load_launch_plan",
    "resolver_snapshot",
    "semantic_sha256",
    "verify_frozen_launch_plan",
    "write_launch_plan",
]
