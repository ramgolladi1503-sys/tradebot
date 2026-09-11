"""Fail-closed Morning Readiness V1 state machine.

This module is deliberately broker-agnostic. It models readiness evidence and
never grants trading authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class MorningState(str, Enum):
    RELEASE_FROZEN = "RELEASE_FROZEN"
    OFFLINE_CERTIFIED = "OFFLINE_CERTIFIED"
    MORNING_PRECHECK = "MORNING_PRECHECK"
    AUTH_READY = "AUTH_READY"
    STORAGE_READY = "STORAGE_READY"
    UNIVERSE_READY = "UNIVERSE_READY"
    SUBSCRIPTION_PLAN_READY = "SUBSCRIPTION_PLAN_READY"
    PERSISTENCE_READY = "PERSISTENCE_READY"
    EVIDENCE_WRITER_READY = "EVIDENCE_WRITER_READY"
    OPTION_MIRROR_OFFLINE_READY = "OPTION_MIRROR_OFFLINE_READY"
    PREOPEN_ARMED = "PREOPEN_ARMED"
    WAITING_FOR_MARKET = "WAITING_FOR_MARKET"
    LIVE_FEED_PENDING = "LIVE_FEED_PENDING"
    LIVE_RUNNING = "LIVE_RUNNING"
    LIVE_DEGRADED = "LIVE_DEGRADED"
    FAIL_CLOSED = "FAIL_CLOSED"
    SHUTDOWN_REQUESTED = "SHUTDOWN_REQUESTED"
    DRAINING = "DRAINING"
    SEALING = "SEALING"
    SEALED = "SEALED"


FATAL_INVARIANTS = frozenset({
    "WRONG_RELEASE_SHA", "DIRTY_WORKTREE", "WRONG_STORAGE_AUTHORITY",
    "REPOSITORY_LOCAL_LIVE_WRITER", "EVIDENCE_ROOT_COLLISION",
    "EVIDENCE_CORRUPTION", "WRITER_DEAD_WITH_PERSISTENCE_LOSS",
    "QUEUE_SATURATION_WITH_LOSS", "AUTHORITY_ESCALATION", "SEAL_CORRUPTION",
    "PROCESS_INTEGRITY_FAILURE",
})
NON_FATAL_INVARIANTS = frozenset({
    "NO_LIVE_OPTION_FEED", "STALE_OPTION_FEED", "CAS_INPUT_UNAVAILABLE",
    "NO_ELIGIBLE_CANDIDATE", "RANKING_UNAVAILABLE", "STRATEGY_UNAVAILABLE",
    "CANDIDATE_PROMOTION_BLOCKED", "OPTION_MIRROR_STALE",
})


ALLOWED: dict[MorningState, frozenset[MorningState]] = {
    MorningState.RELEASE_FROZEN: frozenset({MorningState.OFFLINE_CERTIFIED, MorningState.FAIL_CLOSED}),
    MorningState.OFFLINE_CERTIFIED: frozenset({MorningState.MORNING_PRECHECK, MorningState.FAIL_CLOSED}),
    MorningState.MORNING_PRECHECK: frozenset({MorningState.AUTH_READY, MorningState.FAIL_CLOSED}),
    MorningState.AUTH_READY: frozenset({MorningState.STORAGE_READY, MorningState.FAIL_CLOSED}),
    MorningState.STORAGE_READY: frozenset({MorningState.UNIVERSE_READY, MorningState.FAIL_CLOSED}),
    MorningState.UNIVERSE_READY: frozenset({MorningState.SUBSCRIPTION_PLAN_READY, MorningState.FAIL_CLOSED}),
    MorningState.SUBSCRIPTION_PLAN_READY: frozenset({MorningState.PERSISTENCE_READY, MorningState.FAIL_CLOSED}),
    MorningState.PERSISTENCE_READY: frozenset({MorningState.EVIDENCE_WRITER_READY, MorningState.FAIL_CLOSED}),
    MorningState.EVIDENCE_WRITER_READY: frozenset({MorningState.OPTION_MIRROR_OFFLINE_READY, MorningState.FAIL_CLOSED}),
    MorningState.OPTION_MIRROR_OFFLINE_READY: frozenset({MorningState.PREOPEN_ARMED, MorningState.FAIL_CLOSED}),
    MorningState.PREOPEN_ARMED: frozenset({MorningState.WAITING_FOR_MARKET, MorningState.FAIL_CLOSED}),
    MorningState.WAITING_FOR_MARKET: frozenset({MorningState.LIVE_FEED_PENDING, MorningState.SHUTDOWN_REQUESTED, MorningState.FAIL_CLOSED}),
    MorningState.LIVE_FEED_PENDING: frozenset({MorningState.LIVE_RUNNING, MorningState.LIVE_DEGRADED, MorningState.FAIL_CLOSED}),
    MorningState.LIVE_RUNNING: frozenset({MorningState.LIVE_DEGRADED, MorningState.SHUTDOWN_REQUESTED, MorningState.FAIL_CLOSED}),
    MorningState.LIVE_DEGRADED: frozenset({MorningState.LIVE_RUNNING, MorningState.SHUTDOWN_REQUESTED, MorningState.FAIL_CLOSED}),
    MorningState.FAIL_CLOSED: frozenset({MorningState.SHUTDOWN_REQUESTED, MorningState.SEALED}),
    MorningState.SHUTDOWN_REQUESTED: frozenset({MorningState.DRAINING, MorningState.FAIL_CLOSED}),
    MorningState.DRAINING: frozenset({MorningState.SEALING, MorningState.FAIL_CLOSED}),
    MorningState.SEALING: frozenset({MorningState.SEALED, MorningState.FAIL_CLOSED}),
    MorningState.SEALED: frozenset(),
}


@dataclass(frozen=True)
class MorningReadiness:
    state: MorningState = MorningState.RELEASE_FROZEN
    evidence: tuple[tuple[str, object], ...] = field(default_factory=tuple)
    safety: Mapping[str, bool] = field(default_factory=lambda: {
        "broker_write_authority": False, "order_authority": False,
        "paper_authorized": False, "live_authorized": False,
    })

    def transition(self, target: MorningState, *, evidence: Mapping[str, object] | None = None) -> "MorningReadiness":
        if target not in ALLOWED[self.state]:
            raise ValueError(f"invalid_morning_transition:{self.state.value}->{target.value}")
        if any(bool(self.safety.get(key)) for key in ("broker_write_authority", "order_authority", "paper_authorized", "live_authorized")):
            raise ValueError("authority_escalation")
        merged = dict(self.evidence)
        merged.update(evidence or {})
        return MorningReadiness(target, tuple(sorted(merged.items())), dict(self.safety))

    def classify(self, invariant: str) -> str:
        if invariant in FATAL_INVARIANTS:
            return "FATAL"
        if invariant in NON_FATAL_INVARIANTS:
            return "NON_FATAL"
        return "UNKNOWN_FAIL_CLOSED"

    def degraded_for(self, invariant: str) -> "MorningReadiness":
        if self.classify(invariant) != "NON_FATAL":
            return self.transition(MorningState.FAIL_CLOSED, evidence={"fatal_invariant": invariant})
        if self.state not in {MorningState.LIVE_RUNNING, MorningState.LIVE_DEGRADED}:
            raise ValueError("degraded_mode_requires_live_state")
        return MorningReadiness(MorningState.LIVE_DEGRADED, tuple(sorted({**dict(self.evidence), "degraded_invariant": invariant}.items())), dict(self.safety))


__all__ = ["ALLOWED", "FATAL_INVARIANTS", "NON_FATAL_INVARIANTS", "MorningReadiness", "MorningState"]
