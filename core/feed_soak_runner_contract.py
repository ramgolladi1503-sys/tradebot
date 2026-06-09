"""Read-only feed soak runner contract for FEED-STAB-08.

This module validates soak-runner intent and result evidence without starting
any runtime loop, mutating state, calling brokers, or writing files. It is a
pure contract layer that helps later PRs prove soak readiness from supplied
evidence only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

FEED_SOAK_RUNNER_CONTRACT_SCHEMA_VERSION = 1
FEED_SOAK_RUNNER_CONTRACT_SOURCE = "feed_soak_runner_contract_v1"

SOAK_RUNNER_READY = "SOAK_RUNNER_READY"
SOAK_RUNNER_BLOCKED = "SOAK_RUNNER_BLOCKED"
SOAK_RUNNER_NEEDS_INPUT = "SOAK_RUNNER_NEEDS_INPUT"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class FeedSoakRunnerContract:
    schema_version: int
    source: str
    read_only: bool
    append: bool
    contract_state: str
    runner_ready: bool
    soak_minutes: int
    warmup_minutes: int
    required_cycles: int
    journal_path: str
    output_path: str
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
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(items: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item).strip().upper() for item in items if str(item).strip()))


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def build_feed_soak_runner_contract(payload: Mapping[str, Any] | None) -> FeedSoakRunnerContract:
    source = _as_mapping(payload)
    soak_minutes = _as_int(source.get("soak_minutes") or 0)
    warmup_minutes = _as_int(source.get("warmup_minutes") or 0)
    required_cycles = _as_int(source.get("required_clean_cycles") or source.get("required_cycles") or 0)
    journal_path = _text(source.get("journal_path"))
    output_path = _text(source.get("output_path"))
    state = _text(source.get("runner_state") or source.get("state") or source.get("contract_state")).upper()
    if not state:
        state = SOAK_RUNNER_NEEDS_INPUT

    blockers: list[str] = []
    warnings: list[str] = []

    if soak_minutes <= 0:
        blockers.append("SOAK_MINUTES_REQUIRED")
    if warmup_minutes < 0:
        blockers.append("WARMUP_MINUTES_INVALID")
    if required_cycles <= 0:
        blockers.append("REQUIRED_CYCLES_REQUIRED")
    if not journal_path:
        blockers.append("JOURNAL_PATH_REQUIRED")
    if not output_path:
        blockers.append("OUTPUT_PATH_REQUIRED")
    if _text(source.get("checks_state")).upper() in {"RED", "FAILED", "BLOCKED"}:
        blockers.append("CHECKS_NOT_GREEN")
    if _text(source.get("controller_state")).upper() in {"STOPPED", "BROKEN"}:
        blockers.append("CONTROLLER_NOT_READY")

    runner_ready = not blockers and state in {SOAK_RUNNER_READY, "READY"}
    if runner_ready:
        contract_state = SOAK_RUNNER_READY
    elif blockers:
        contract_state = SOAK_RUNNER_BLOCKED
    else:
        contract_state = SOAK_RUNNER_NEEDS_INPUT
        warnings.append("SOAK_RUNNER_NEEDS_INPUT")

    return FeedSoakRunnerContract(
        schema_version=FEED_SOAK_RUNNER_CONTRACT_SCHEMA_VERSION,
        source=FEED_SOAK_RUNNER_CONTRACT_SOURCE,
        read_only=True,
        append=False,
        contract_state=contract_state,
        runner_ready=runner_ready,
        soak_minutes=soak_minutes,
        warmup_minutes=warmup_minutes,
        required_cycles=required_cycles,
        journal_path=journal_path,
        output_path=output_path,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        metadata={
            "does_not_mutate_runtime": True,
            "does_not_call_broker": True,
            "does_not_emit_order_actions": True,
            "does_not_write_files": False,
        },
    )


__all__ = [
    "FEED_SOAK_RUNNER_CONTRACT_SCHEMA_VERSION",
    "FEED_SOAK_RUNNER_CONTRACT_SOURCE",
    "FeedSoakRunnerContract",
    "SOAK_RUNNER_BLOCKED",
    "SOAK_RUNNER_NEEDS_INPUT",
    "SOAK_RUNNER_READY",
    "build_feed_soak_runner_contract",
]
