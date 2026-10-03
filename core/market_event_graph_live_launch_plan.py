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


def _tokens(values: Any) -> list[int]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        token = _positive_int(value)
        if token is not None and token not in seen:
            result.append(token)
            seen.add(token)
    return result


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _strict_token_list(values: Any) -> list[int] | None:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return None
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        token = _positive_int(value)
        if token is None or token in seen:
            return None
        result.append(token)
        seen.add(token)
    return result


def _resolution_token_sets(
    *,
    production_tokens: Sequence[int],
    production_resolution: Any,
    sticky_tokens: Sequence[int],
) -> tuple[set[int], set[int]] | None:
    """Return exact underlying/option ownership sets or reject ambiguous rows."""
    production = set(production_tokens)
    sticky = set(sticky_tokens)
    if not production or not sticky.issubset(production):
        return None
    if not isinstance(production_resolution, list) or not production_resolution:
        return None

    underlying: set[int] = set()
    options: set[int] = set()
    owned: set[int] = set()
    symbols: set[str] = set()
    for row in production_resolution:
        if not isinstance(row, Mapping):
            return None
        symbol = str(row.get("symbol") or "").strip().upper()
        index_token = _positive_int(row.get("index_token"))
        row_tokens = _strict_token_list(row.get("tokens"))
        if not symbol or symbol in symbols or index_token is None or not row_tokens:
            return None
        row_token_set = set(row_tokens)
        if index_token not in row_token_set or row_token_set & sticky or row_token_set & owned:
            return None
        option_tokens = row_token_set - {index_token}
        expected_option_count = len(option_tokens)
        if not any(key in row for key in ("final_option_count", "option_count")):
            return None
        for count_key in ("final_option_count", "option_count"):
            if count_key in row:
                declared = row.get(count_key)
                parsed_count = _nonnegative_int(declared)
                if parsed_count is None or parsed_count != expected_option_count:
                    return None
        min_required = row.get("option_min_required")
        if _positive_int(min_required) is None:
            return None
        symbols.add(symbol)
        owned.update(row_token_set)
        underlying.add(index_token)
        options.update(option_tokens)

    if owned | sticky != production or owned & sticky:
        return None
    return underlying, options


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
    production_input = _strict_token_list(production_tokens)
    observation_input = _strict_token_list(observation_tokens)
    sticky_input = _strict_token_list(sticky_tokens)
    production = _tokens(production_tokens)
    observation = _tokens(observation_tokens)
    sticky = _tokens(sticky_tokens)
    try:
        resolution = [_json_safe(dict(row)) for row in production_resolution]
    except (TypeError, ValueError):
        resolution = []
    identity_sets = _resolution_token_sets(
        production_tokens=production,
        production_resolution=resolution,
        sticky_tokens=sticky,
    )
    underlying_set, option_set = identity_sets if identity_sets is not None else (set(), set())
    underlying = sorted(underlying_set)
    option_tokens = sorted(option_set)
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
    complete_union = set(basis["final_union_tokens"]) == set(production) | set(observation)
    ok = bool(
        merge["ok"]
        and len(observation) == 51
        and complete_union
        and identity_sets is not None
        and production_input is not None
        and observation_input is not None
        and sticky_input is not None
    )
    if not merge["ok"]:
        verdict = str(merge["reason"])
    elif not ok:
        verdict = BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN
    else:
        verdict = PASS_LIVE_SOURCE_PRESESSION_READINESS
    return {
        **basis,
        "ok": ok,
        "verdict": verdict,
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
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
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
    if (
        claimed != _sha(basis)
        or raw.get("ok") is not True
        or raw.get("verdict") != PASS_LIVE_SOURCE_PRESESSION_READINESS
        or raw.get("read_only") is not True
        or raw.get("append") is not False
        or raw.get("is_order_action") is not False
        or raw.get("broker_api_called") is not False
        or raw.get("allowed_for_live_execution") is not False
    ):
        raise ValueError(BLOCKED_BY_LAUNCH_PLAN_IDENTITY)
    production = _strict_token_list(raw.get("production_tokens"))
    observation = _strict_token_list(raw.get("observation_tokens"))
    sticky = _strict_token_list(raw.get("production_sticky_tokens"))
    final_union = _strict_token_list(raw.get("final_union_tokens"))
    identity_sets = (
        _resolution_token_sets(
            production_tokens=production,
            production_resolution=raw.get("production_resolution"),
            sticky_tokens=sticky,
        )
        if production is not None and sticky is not None
        else None
    )
    if production is None or observation is None or sticky is None or final_union is None or identity_sets is None:
        raise ValueError(BLOCKED_BY_LAUNCH_PLAN_IDENTITY)
    underlying, options = identity_sets
    configured_budget = _nonnegative_int(raw.get("configured_budget"))
    option_count = _nonnegative_int(raw.get("production_option_count"))
    expected_counts = {
        "production_token_count": len(production),
        "production_underlying_count": len(underlying),
        "production_option_count": len(options),
        "production_sticky_count": len(sticky),
        "observation_token_count": len(observation),
        "overlap_count": len(set(production) & set(observation)),
        "observation_exclusive_count": len(set(observation) - set(production)),
        "final_union_count": len(final_union),
    }
    overlap_tokens = _strict_token_list(raw.get("overlap_tokens"))
    observation_exclusive = _strict_token_list(raw.get("observation_exclusive_tokens"))
    missing_observation = _strict_token_list(raw.get("missing_observation_tokens"))
    if (
        len(observation) != 51
        or set(_strict_token_list(raw.get("production_underlying_tokens")) or []) != underlying
        or set(_strict_token_list(raw.get("production_option_tokens")) or []) != options
        or set(_strict_token_list(raw.get("production_sticky_tokens")) or []) != set(sticky)
        or overlap_tokens is None
        or set(overlap_tokens) != set(production) & set(observation)
        or observation_exclusive is None
        or set(observation_exclusive) != set(observation) - set(production)
        or missing_observation != []
        or set(final_union) != set(production) | set(observation)
        or configured_budget is None
        or option_count != len(options)
        or len(final_union) > configured_budget
        or any(_nonnegative_int(raw.get(key)) != value for key, value in expected_counts.items())
    ):
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
