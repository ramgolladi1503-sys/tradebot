"""Evidence-gated state machine for canonical read-only observation sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class LiveState(StrEnum):
    OFFLINE_PREFLIGHT = "OFFLINE_PREFLIGHT"
    READ_AUTH = "READ_AUTH"
    INSTRUMENT_AUTHORITY = "INSTRUMENT_AUTHORITY"
    FEED_HEALTH = "FEED_HEALTH"
    PERSISTENCE_HEALTH = "PERSISTENCE_HEALTH"
    MARKET_PRIMITIVES = "MARKET_PRIMITIVES"
    REGIME_PIPELINE = "REGIME_PIPELINE"
    STRATEGY_EMISSION = "STRATEGY_EMISSION"
    OPTION_SURFACE = "OPTION_SURFACE"
    ELIGIBILITY = "ELIGIBILITY"
    RANKING_PIPELINE = "RANKING_PIPELINE"
    ADVISORY_QUEUE = "ADVISORY_QUEUE"
    LIVE_VERIFIED = "LIVE_VERIFIED"
    MARKET_CLOSE_STOP = "MARKET_CLOSE_STOP"
    PERSISTENCE_FLUSH = "PERSISTENCE_FLUSH"
    SESSION_SEALED = "SESSION_SEALED"
    NO_RESPAWN_PROOF = "NO_RESPAWN_PROOF"


_ORDER = tuple(LiveState)


@dataclass
class LifecycleEvidence:
    states: dict[str, str] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)

    def record(self, state: LiveState, verdict: str, **facts: Any) -> None:
        verdict = str(verdict).upper()
        if verdict not in {"PASS", "PENDING", "FAIL", "NO_TRADE"}:
            raise ValueError("invalid_lifecycle_verdict")
        self.states[state.value] = verdict
        self.facts.update(facts)

    def can_promote(self, state: LiveState) -> bool:
        if state is LiveState.LIVE_VERIFIED:
            required = (
                LiveState.READ_AUTH, LiveState.INSTRUMENT_AUTHORITY,
                LiveState.FEED_HEALTH, LiveState.PERSISTENCE_HEALTH,
                LiveState.MARKET_PRIMITIVES, LiveState.REGIME_PIPELINE,
                LiveState.STRATEGY_EMISSION, LiveState.OPTION_SURFACE,
                LiveState.ELIGIBILITY, LiveState.RANKING_PIPELINE,
                LiveState.ADVISORY_QUEUE,
            )
            if any(self.states.get(item.value) not in {"PASS", "NO_TRADE"} for item in required):
                return False
            return (
                self.facts.get("fresh_ticks") is True
                and self.facts.get("feed_owner_count") == 1
                and self.facts.get("broker_write_authority") is False
                and self.facts.get("order_authority") is False
            )
        if state is LiveState.SESSION_SEALED:
            return all(self.states.get(item.value) == "PASS" for item in (
                LiveState.MARKET_CLOSE_STOP, LiveState.PERSISTENCE_FLUSH,
                LiveState.NO_RESPAWN_PROOF,
            ))
        return self.states.get(state.value) in {"PASS", "NO_TRADE"}

    def promote(self, state: LiveState) -> None:
        if not self.can_promote(state):
            raise RuntimeError(f"LIFECYCLE_PROMOTION_BLOCKED:{state.value}")
        self.states[state.value] = "PASS"


def validate_read_only_snapshot(snapshot: Mapping[str, Any]) -> None:
    for key in ("broker_write_authority", "order_authority", "paper_authorized", "live_execution_authorized"):
        if snapshot.get(key) is not False:
            raise ValueError(f"read_only_snapshot_authority_not_false:{key}")
    if snapshot.get("orders_placed", 0) != 0 or snapshot.get("orders_modified", 0) != 0 or snapshot.get("orders_cancelled", 0) != 0:
        raise ValueError("read_only_snapshot_order_count_nonzero")
