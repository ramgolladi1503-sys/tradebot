"""Explicit runtime hook for terminal paper-order outcomes.

This module is the narrow integration point runtime owners can call when they
transition a paper order. It keeps the pure state machine pure: callers opt into
journal persistence by using this hook instead of changing transition semantics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from core.paper_order_state_machine import PaperOrderRecord, TERMINAL_STATES, transition_paper_order
from core.paper_terminal_outcome_wiring import record_terminal_paper_outcome

PAPER_RUNTIME_OUTCOME_HOOK_SCHEMA_VERSION = 1


class PaperRuntimeOutcomeHookError(ValueError):
    """Raised when runtime terminal outcome hook input is invalid."""


@dataclass(frozen=True)
class PaperRuntimeOutcomeHookResult:
    schema_version: int
    paper_order_id: str
    from_state: str
    to_state: str
    terminal: bool
    outcome_recorded: bool
    journal_record: dict[str, Any] | None
    reason: str
    warnings: tuple[str, ...]
    metadata: dict[str, Any]

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        payload["metadata"] = dict(self.metadata)
        payload["is_order_action"] = self.is_order_action
        payload["broker_api_called"] = self.broker_api_called
        payload["live_order_action"] = self.live_order_action
        payload["broker_order_action"] = self.broker_order_action
        return payload


def transition_paper_order_and_record_outcome(
    order: PaperOrderRecord,
    to_state: str,
    *,
    reason: str,
    event_id: str | None = None,
    filled_quantity_delta: int = 0,
    outcome_defaults: Mapping[str, Any] | None = None,
    records_path: str | Path | None = None,
    state_path: str | Path | None = None,
) -> tuple[PaperOrderRecord, PaperRuntimeOutcomeHookResult]:
    """Transition a paper order and record an outcome only if it becomes terminal."""

    if not isinstance(order, PaperOrderRecord):
        raise PaperRuntimeOutcomeHookError("paper_runtime_hook_requires_paper_order_record")

    previous_state = str(order.state or "")
    updated_order = transition_paper_order(
        order,
        to_state,
        reason=reason,
        event_id=event_id,
        filled_quantity_delta=filled_quantity_delta,
    )
    terminal = str(updated_order.state or "") in TERMINAL_STATES
    journal_record = None
    warnings: list[str] = []

    if terminal:
        journal_record = record_terminal_paper_outcome(
            updated_order,
            defaults=outcome_defaults,
            records_path=records_path,
            state_path=state_path,
        )
    else:
        warnings.append("paper_order_not_terminal_no_journal_record")

    result = PaperRuntimeOutcomeHookResult(
        schema_version=PAPER_RUNTIME_OUTCOME_HOOK_SCHEMA_VERSION,
        paper_order_id=str(updated_order.paper_order_id),
        from_state=previous_state,
        to_state=str(updated_order.state),
        terminal=terminal,
        outcome_recorded=journal_record is not None,
        journal_record=journal_record,
        reason=str(reason or "").strip() or "paper_runtime_transition",
        warnings=tuple(warnings),
        metadata={
            "hook": "paper_runtime_outcome_hook_v1",
            "state_machine_preserved_pure": True,
            "source_of_truth": "family_outcomes_jsonl",
        },
    )
    return updated_order, result


__all__ = [
    "PAPER_RUNTIME_OUTCOME_HOOK_SCHEMA_VERSION",
    "PaperRuntimeOutcomeHookError",
    "PaperRuntimeOutcomeHookResult",
    "transition_paper_order_and_record_outcome",
]
