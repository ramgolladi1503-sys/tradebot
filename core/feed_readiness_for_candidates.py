from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


FEED_READINESS_FOR_CANDIDATES_SCHEMA_VERSION = 1
FEED_READINESS_FOR_CANDIDATES_SOURCE = "feed_readiness_for_candidates_v1"

READINESS_STATE_READY = "READY"
READINESS_STATE_WARMING_UP = "WARMING_UP"
READINESS_STATE_BLOCKED = "BLOCKED"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class FeedReadinessForCandidatesContract:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    readiness_state: str
    candidate_generation_allowed: bool
    feed_supervisor_state: str
    feed_supervisor_reason_code: str
    warmup_clean_cycles: int
    warmup_required_clean_cycles: int
    clean_cycles_remaining: int
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def ready(self) -> bool:
        return self.candidate_generation_allowed and self.readiness_state == READINESS_STATE_READY

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["ready"] = self.ready
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _dedupe(items: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item).strip().upper() for item in items if str(item).strip()))


def build_feed_readiness_for_candidates_contract(snapshot: Mapping[str, Any] | None) -> FeedReadinessForCandidatesContract:
    source = _as_mapping(snapshot)
    supervisor = _as_mapping(source.get("feed_supervisor") or source.get("supervisor") or source)
    state = _upper(supervisor.get("state") or source.get("state"))
    reason_code = _upper(supervisor.get("reason_code") or source.get("reason_code") or state or "UNKNOWN")

    warmup_clean_cycles = max(0, _as_int(supervisor.get("warmup_clean_cycles") or source.get("warmup_clean_cycles")))
    warmup_required_clean_cycles = max(1, _as_int(supervisor.get("warmup_required_clean_cycles") or source.get("warmup_required_clean_cycles") or 3))
    clean_cycles_remaining = max(0, warmup_required_clean_cycles - warmup_clean_cycles)

    blockers: list[str] = []
    warnings: list[str] = []

    if state in {"AUTH_REQUIRED", "RESTART_REQUIRED", "RECOVERY_BLOCKED", "RECOVERY_TIMEOUT"}:
        blockers.append(state)
    if state in {"RECOVERING", "VERIFYING", "WARMING_UP", "CONNECTED", "SUBSCRIBED", "CONNECTING", "BOOTING"} and clean_cycles_remaining > 0:
        warnings.append("WARMUP_NOT_COMPLETE")
    if state == "CANDIDATE_READY":
        blockers = []
        warnings = []

    candidate_generation_allowed = state == "CANDIDATE_READY" and not blockers and clean_cycles_remaining == 0
    readiness_state = (
        READINESS_STATE_READY
        if candidate_generation_allowed
        else READINESS_STATE_BLOCKED
        if blockers or state in {"AUTH_REQUIRED", "RESTART_REQUIRED", "RECOVERY_BLOCKED", "RECOVERY_TIMEOUT"}
        else READINESS_STATE_WARMING_UP
    )

    return FeedReadinessForCandidatesContract(
        schema_version=FEED_READINESS_FOR_CANDIDATES_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=FEED_READINESS_FOR_CANDIDATES_SOURCE,
        readiness_state=readiness_state,
        candidate_generation_allowed=candidate_generation_allowed,
        feed_supervisor_state=state or "UNKNOWN",
        feed_supervisor_reason_code=reason_code or "UNKNOWN",
        warmup_clean_cycles=warmup_clean_cycles,
        warmup_required_clean_cycles=warmup_required_clean_cycles,
        clean_cycles_remaining=clean_cycles_remaining,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        metadata={
            "does_not_import_strategy_modules": True,
            "does_not_execute_strategy_callables": True,
            "does_not_rank_candidates": True,
            "does_not_score_edge": True,
            "does_not_select_candidates": True,
            "does_not_allocate_capital": True,
        },
    )


__all__ = [
    "FEED_READINESS_FOR_CANDIDATES_SCHEMA_VERSION",
    "FEED_READINESS_FOR_CANDIDATES_SOURCE",
    "FeedReadinessForCandidatesContract",
    "READINESS_STATE_BLOCKED",
    "READINESS_STATE_READY",
    "READINESS_STATE_WARMING_UP",
    "build_feed_readiness_for_candidates_contract",
]
