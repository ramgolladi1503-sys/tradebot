"""Cached Kite market-event-graph observation registry.

This registry is read-only and advisory. It loads the authoritative Kite
contract once, validates the exact 51-token observation identity, and exposes a
cached token lookup for websocket subscription and raw tick routing.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from config import config as cfg
from core.market_event_graph_live_runtime_bridge import canonical_live_universe_sha256

BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET = "BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET"
BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE = "BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE"


@dataclass(frozen=True)
class ObservationRegistry:
    contract_path: str
    canonical_sha256: str
    provider: str
    token_domain: str
    index_symbol: str
    index_token: int
    token_by_symbol: Mapping[str, int]
    symbol_by_token: Mapping[int, str]
    instrument_class_by_token: Mapping[int, str]
    constituent_symbols: tuple[str, ...]
    constituent_tokens: tuple[int, ...]
    all_tokens: tuple[int, ...]
    contract: Mapping[str, Any]

    @property
    def token_count(self) -> int:
        return len(self.all_tokens)

    def observation_identity(self, token: int) -> dict[str, Any] | None:
        token_int = int(token)
        symbol = self.symbol_by_token.get(token_int)
        if symbol is None:
            return None
        return {
            "symbol": symbol,
            "instrument_token": token_int,
            "instrument_class": self.instrument_class_by_token.get(token_int, "UNKNOWN"),
            "provider": self.provider,
            "token_domain": self.token_domain,
            "universe_hash": self.canonical_sha256,
        }


_OBSERVATION_REGISTRY: ObservationRegistry | None = None
_OBSERVATION_REGISTRY_IDENTITY: tuple[str, str, str] | None = None


def reset_observation_registry() -> None:
    global _OBSERVATION_REGISTRY, _OBSERVATION_REGISTRY_IDENTITY
    _OBSERVATION_REGISTRY = None
    _OBSERVATION_REGISTRY_IDENTITY = None


def _contract_path() -> Path | None:
    path_text = str(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", "") or "").strip()
    if not path_text:
        return None
    return Path(path_text)


def load_observation_registry(*, force: bool = False) -> ObservationRegistry | None:
    global _OBSERVATION_REGISTRY, _OBSERVATION_REGISTRY_IDENTITY
    if not bool(getattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)):
        reset_observation_registry()
        return None
    path = _contract_path()
    if path is None or not path.exists():
        raise FileNotFoundError(path or "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH")
    contract_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    raw = json.loads(path.read_text(encoding="utf-8"))
    canonical = str(raw.get("canonical_sha256") or "") if isinstance(raw, Mapping) else ""
    identity = (str(path.resolve()), contract_sha, canonical)
    if _OBSERVATION_REGISTRY is not None and not force and _OBSERVATION_REGISTRY_IDENTITY == identity:
        return _OBSERVATION_REGISTRY
    if not isinstance(raw, Mapping):
        raise ValueError("live universe contract must be a JSON object")
    provider = str(raw.get("broker_provider") or "").lower().strip()
    token_domain = str(raw.get("token_domain") or "").lower().strip()
    if provider != "kite" or token_domain != "kite_instrument_token":
        raise ValueError(BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE)
    if str(raw.get("official_raw_sha256") or "") != "9fb8832853c279448d2bc05f0e7dd5f460ed2ff35332fea8c40fc1250362ad28":
        raise ValueError(BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE)
    master = dict(raw.get("broker_instrument_master") or {})
    if str(master.get("sha256") or "") != "828c0c378e4939720c34ee7e727e5ae6f0265441e0e0a1888a386f85ab9c2a93":
        raise ValueError(BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE)
    constituents = tuple(dict(row) for row in raw.get("constituents") or [])
    if len(constituents) != 50:
        raise ValueError(BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE)
    symbols = [str(row["symbol"]).upper() for row in constituents]
    tokens = [int(row["instrument_token"]) for row in constituents]
    if len(set(symbols)) != len(symbols) or len(set(tokens)) != len(tokens):
        raise ValueError(BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE)
    index_symbol = str(raw.get("index_symbol") or "NIFTY").upper()
    index_token = int(raw["index_instrument_token"])
    if index_symbol != "NIFTY" or index_token != 256265 or index_token in tokens:
        raise ValueError(BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE)
    token_by_symbol = {index_symbol: index_token, **{sym: tok for sym, tok in zip(symbols, tokens)}}
    all_tokens = tuple(sorted(set(token_by_symbol.values())))
    if len(all_tokens) != 51:
        raise ValueError(BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE)
    if canonical != canonical_live_universe_sha256(raw):
        raise ValueError(BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE)
    instrument_class_by_token = {index_token: "INDEX"}
    for token in tokens:
        instrument_class_by_token[token] = "NSE_EQUITY"
    registry = ObservationRegistry(
        contract_path=str(path),
        canonical_sha256=canonical,
        provider=provider,
        token_domain=token_domain,
        index_symbol=index_symbol,
        index_token=index_token,
        token_by_symbol=MappingProxyType(token_by_symbol),
        symbol_by_token=MappingProxyType({token: symbol for symbol, token in token_by_symbol.items()}),
        instrument_class_by_token=MappingProxyType(instrument_class_by_token),
        constituent_symbols=tuple(symbols),
        constituent_tokens=tuple(tokens),
        all_tokens=all_tokens,
        contract=MappingProxyType(dict(raw)),
    )
    _OBSERVATION_REGISTRY = registry
    _OBSERVATION_REGISTRY_IDENTITY = identity
    return registry


def get_observation_registry() -> ObservationRegistry | None:
    return load_observation_registry(force=False)


def observation_tokens() -> set[int]:
    registry = get_observation_registry()
    return set(registry.all_tokens) if registry is not None else set()


def observation_budget_preflight(*, budget: int | None, current_tokens: list[int], overlap_tokens: set[int] | None = None) -> dict[str, Any]:
    registry = get_observation_registry()
    if registry is None:
        return {"ok": True, "reason": "DISABLED", "observation_count": 0}
    current = {int(token) for token in current_tokens if int(token) > 0}
    overlap = set(int(token) for token in (overlap_tokens or set()) if int(token) > 0)
    added = set(registry.all_tokens) - current
    effective_total = len(current | set(registry.all_tokens))
    ok = budget is None or effective_total <= int(budget)
    return {
        "ok": ok,
        "reason": "OK" if ok else BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET,
        "provider": registry.provider,
        "token_domain": registry.token_domain,
        "observation_count": len(registry.all_tokens),
        "current_count": len(current),
        "overlap_count": len(overlap),
        "added_count": len(added),
        "configured_budget": budget,
        "post_merge_count": effective_total,
        "missing_tokens": sorted(int(token) for token in set(registry.all_tokens) - current),
        "pruned_tokens": [],
        "contract_path": registry.contract_path,
        "canonical_sha256": registry.canonical_sha256,
    }


def build_observation_subscription_merge(*, production_tokens: list[int], observation_tokens: list[int], budget: int | None) -> dict[str, Any]:
    production = tuple(dict.fromkeys(int(token) for token in production_tokens if int(token) > 0))
    observation = tuple(dict.fromkeys(int(token) for token in observation_tokens if int(token) > 0))
    overlap = set(production) & set(observation)
    union = tuple(dict.fromkeys(production + observation))
    ok = budget is None or len(union) <= int(budget)
    return {
        "ok": ok, "reason": "OK" if ok else BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET,
        "production_token_count": len(production), "observation_token_count": len(observation),
        "overlap_count": len(overlap), "observation_exclusive_count": len(set(observation) - set(production)),
        "final_union_count": len(union), "configured_budget": budget,
        "missing_or_pruned_observation_tokens": [] if ok else list(observation),
        "tokens": list(union) if ok else list(production),
    }


__all__ = [
    "BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE",
    "BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET",
    "ObservationRegistry",
    "get_observation_registry",
    "load_observation_registry",
    "observation_budget_preflight",
    "build_observation_subscription_merge",
    "reset_observation_registry",
    "observation_tokens",
]
