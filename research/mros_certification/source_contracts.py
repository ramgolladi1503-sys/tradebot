"""Frozen Global Context V2 source-contract declarations."""
from dataclasses import dataclass
from typing import Mapping

@dataclass(frozen=True)
class SourceContract:
    name: str
    authority: str
    timezone: str
    units: str
    causal_cutoff: str
    freshness_seconds: int
    missing_status: str = "BLOCKED_DATA"

def freeze_source_contracts(contracts: tuple[SourceContract, ...]) -> Mapping[str, object]:
    if not contracts or len({c.name for c in contracts}) != len(contracts): raise ValueError("SOURCE_CONTRACT_DUPLICATE")
    if any(not c.authority or c.freshness_seconds <= 0 for c in contracts): raise ValueError("SOURCE_AUTHORITY_REQUIRED")
    return {"version": "GLOBAL_CONTEXT_V2", "sources": tuple(contracts), "immutable": True, "status": "SPEC_FROZEN"}
