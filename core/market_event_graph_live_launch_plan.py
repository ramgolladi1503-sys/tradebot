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
PASS_STATIC_LIVE_SOURCE_PREFLIGHT = "PASS_STATIC_LIVE_SOURCE_PREFLIGHT"
PASS_LIVE_SOURCE_PRESESSION_READINESS = "PASS_LIVE_SOURCE_PRESESSION_READINESS"
BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN = "BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN"
BLOCKED_BY_LAUNCH_PLAN_IDENTITY = "BLOCKED_BY_LAUNCH_PLAN_IDENTITY"


def _tokens(values: Sequence[int]) -> list[int]:
    return list(dict.fromkeys(int(value) for value in values if int(value) > 0))


def _sha(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


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


__all__ = [
    "BLOCKED_BY_LAUNCH_PLAN_IDENTITY",
    "BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN",
    "PASS_STATIC_LIVE_SOURCE_PREFLIGHT",
    "PASS_LIVE_SOURCE_PRESESSION_READINESS",
    "build_launch_plan",
    "load_launch_plan",
    "write_launch_plan",
]
