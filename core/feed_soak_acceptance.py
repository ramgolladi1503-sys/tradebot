from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


FEED_SOAK_ACCEPTANCE_CONTRACT_SCHEMA_VERSION = 1
FEED_SOAK_ACCEPTANCE_CONTRACT_SOURCE = "feed_soak_acceptance_contract_v1"

SOAK_ACCEPTANCE_READY = "SOAK_ACCEPTANCE_READY"
SOAK_ACCEPTANCE_BLOCKED = "SOAK_ACCEPTANCE_BLOCKED"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class FeedSoakAcceptanceContract:
    schema_version: int
    source: str
    read_only: bool
    append: bool
    acceptance_state: str
    accepted: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _dedupe(items: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item).strip().upper() for item in items if str(item).strip()))


def _truthy(*values: Any) -> bool:
    return any(_upper(value) in {"1", "TRUE", "YES", "Y", "OK", "LIVE", "HEALTHY", "FRESH"} for value in values)


def build_feed_soak_acceptance_contract(payload: Mapping[str, Any] | None) -> FeedSoakAcceptanceContract:
    source = _as_mapping(payload)
    runtime = _as_mapping(source.get("runtime") or source.get("feed_runtime") or source)
    supervisor = _as_mapping(source.get("feed_supervisor") or source.get("supervisor") or source)

    feed_truth_state = _upper(runtime.get("feed_truth_state") or source.get("feed_truth_state"))
    feed_truth_reason_code = _upper(runtime.get("feed_truth_reason_code") or source.get("feed_truth_reason_code"))
    restart_failure_reason = _upper(
        runtime.get("restart_failure_reason")
        or source.get("restart_failure_reason")
        or runtime.get("restart_blocked_reason")
        or runtime.get("reconnect_blocked_reason")
    )
    process_restart_required = _truthy(runtime.get("process_restart_required") or source.get("process_restart_required"))
    dead_without_recovery = feed_truth_state == "DEAD" and not process_restart_required and not _truthy(runtime.get("recovery_blocked") or source.get("recovery_blocked"))
    no_live_option_feed = any(
        _upper(reason) == "NO_LIVE_OPTION_FEED"
        for reason in (
            runtime.get("option_feed_block_reason"),
            *(runtime.get("option_feed_block_reason_by_symbol") or {}).values(),
        )
    ) or "NO_LIVE_OPTION_FEED" in _dedupe(list(runtime.get("feed_truth_reasons") or []))
    persistent_stale_feed = _truthy(
        source.get("persistent_stale_feed"),
        source.get("stale_feed_persistent"),
        source.get("stale_feed_persisted"),
    ) or any(
        _upper(reason) in {"STALE_OPTION_LTP", "LTP_STALE", "LTP_TICKS_STALE", "DEPTH_STALE", "DEPTH_TICKS_STALE"}
        for reason in list(runtime.get("feed_truth_reasons") or [])
    )
    candidate_ready_under_bad_feed = _upper(supervisor.get("state") or source.get("feed_supervisor_state")) == "CANDIDATE_READY" and (
        feed_truth_state in {"DEAD", "RECOVERY_BLOCKED", "RESTART_REQUIRED"} or no_live_option_feed or process_restart_required
    )
    reactor_terminal = "REACTORNOTRESTARTABLE" in restart_failure_reason or feed_truth_reason_code == "REACTOR_NOT_RESTARTABLE_PROCESS_RESTART_REQUIRED"

    blockers: list[str] = []
    warnings: list[str] = []
    if reactor_terminal:
        blockers.append("REACTOR_NOT_RESTARTABLE")
    if process_restart_required:
        blockers.append("RESTART_REQUIRED")
    if dead_without_recovery:
        blockers.append("DEAD_WITHOUT_RECOVERY")
    if no_live_option_feed:
        blockers.append("NO_LIVE_OPTION_FEED")
    if persistent_stale_feed:
        blockers.append("PERSISTENT_STALE_FEED")
    if candidate_ready_under_bad_feed:
        blockers.append("CANDIDATE_READY_UNDER_BAD_FEED")

    accepted = not blockers
    acceptance_state = SOAK_ACCEPTANCE_READY if accepted else SOAK_ACCEPTANCE_BLOCKED

    return FeedSoakAcceptanceContract(
        schema_version=FEED_SOAK_ACCEPTANCE_CONTRACT_SCHEMA_VERSION,
        source=FEED_SOAK_ACCEPTANCE_CONTRACT_SOURCE,
        read_only=True,
        append=False,
        acceptance_state=acceptance_state,
        accepted=accepted,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        metadata={
            "does_not_mutate_runtime": True,
            "does_not_call_broker": True,
            "does_not_emit_order_actions": True,
            "fail_closed_on_terminal_recovery": True,
        },
    )


__all__ = [
    "FEED_SOAK_ACCEPTANCE_CONTRACT_SCHEMA_VERSION",
    "FEED_SOAK_ACCEPTANCE_CONTRACT_SOURCE",
    "FeedSoakAcceptanceContract",
    "SOAK_ACCEPTANCE_BLOCKED",
    "SOAK_ACCEPTANCE_READY",
    "build_feed_soak_acceptance_contract",
]
