"""Read-only paper outcome reducer for EDGE-84.

The reducer consumes the EDGE-83 paper-truth journal and derives paper state
from validated journal events. The journal remains the source of truth. This
module does not append journal events, call brokers, place live trades, rank
candidates, score opportunities, compute expectancy, or change dashboard/runtime
behavior.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.paper_truth_journal import (
    PAPER_EVENT_CANDIDATE_ACCEPTED,
    PAPER_EVENT_ENTRY_RECORDED,
    PAPER_EVENT_EXIT_RECORDED,
    PAPER_EVENT_NOTE_RECORDED,
    PAPER_EVENT_REJECTED,
    PAPER_MODE,
    PaperTruthJournalValidation,
    read_paper_truth_events,
    validate_paper_truth_events,
)

PAPER_OUTCOME_REDUCER_SCHEMA_VERSION = 1
PAPER_OUTCOME_REDUCER_SOURCE = "paper_outcome_reducer_v1"

PAPER_REDUCER_STATUS_REDUCED = "PAPER_OUTCOMES_REDUCED"
PAPER_REDUCER_STATUS_BLOCKED = "PAPER_OUTCOMES_BLOCKED"

INVALID_JOURNAL_REASON = "invalid_paper_truth_journal"
OPEN_POSITION_REASON = "open_position_without_exit"
EXIT_WITHOUT_ENTRY_REASON = "exit_without_entry"
DUPLICATE_ENTRY_REASON = "duplicate_entry_for_candidate"
REJECTED_CANDIDATE_REASON = "candidate_rejected"
NOTE_ONLY_REASON = "note_only_candidate"
UNHANDLED_EVENT_REASON = "unhandled_paper_event_type"

OUTCOME_OPEN = "OPEN"
OUTCOME_CLOSED = "CLOSED"
OUTCOME_REJECTED = "REJECTED"
OUTCOME_NOTE_ONLY = "NOTE_ONLY"
OUTCOME_INVALID = "INVALID"
OUTCOME_ACCEPTED = "ACCEPTED"

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class PaperCandidateOutcome:
    """Derived paper outcome for one candidate id."""

    candidate_id: str
    strategy_id: str
    symbol: str
    status: str
    entry_side: str = ""
    exit_side: str = ""
    quantity: float = 0.0
    entry_price: float | None = None
    exit_price: float | None = None
    gross_pnl: float | None = None
    first_sequence: int = 0
    latest_sequence: int = 0
    event_count: int = 0
    blockers: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "status": self.status,
            "entry_side": self.entry_side,
            "exit_side": self.exit_side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "gross_pnl": self.gross_pnl,
            "first_sequence": self.first_sequence,
            "latest_sequence": self.latest_sequence,
            "event_count": self.event_count,
            "blockers": list(self.blockers),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PaperOutcomeReductionReport:
    """Read-only report derived from a paper-truth journal."""

    schema_version: int
    source: str
    status: str
    journal_valid: bool
    reason_code: str
    reasons: tuple[str, ...]
    event_count: int
    candidate_count: int
    closed_count: int
    open_count: int
    rejected_count: int
    invalid_count: int
    realized_gross_pnl: float
    outcomes: tuple[PaperCandidateOutcome, ...]
    journal_validation: dict[str, Any]
    read_only: bool = True
    append: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

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

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "source": self.source,
            "status": self.status,
            "journal_valid": self.journal_valid,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "event_count": self.event_count,
            "candidate_count": self.candidate_count,
            "closed_count": self.closed_count,
            "open_count": self.open_count,
            "rejected_count": self.rejected_count,
            "invalid_count": self.invalid_count,
            "realized_gross_pnl": self.realized_gross_pnl,
            "outcomes": [outcome.to_payload() for outcome in self.outcomes],
            "journal_validation": dict(self.journal_validation),
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def reduce_paper_outcomes_from_journal(journal_path: str | Path) -> PaperOutcomeReductionReport:
    """Read and reduce a paper-truth journal file without mutating it."""

    try:
        events = read_paper_truth_events(journal_path)
    except ValueError as exc:
        validation = PaperTruthJournalValidation(
            journal_valid=False,
            reason_code=INVALID_JOURNAL_REASON,
            reasons=(str(exc),),
            event_count=0,
            latest_sequence=0,
            latest_event_hash="",
        )
        return _blocked_report(validation)
    return reduce_paper_outcomes(events)


def reduce_paper_outcomes(events: Iterable[Mapping[str, Any]]) -> PaperOutcomeReductionReport:
    """Validate and reduce paper-truth journal events into candidate outcomes."""

    materialized = tuple(dict(event) for event in events)
    validation = validate_paper_truth_events(materialized)
    if not validation.journal_valid:
        return _blocked_report(validation)

    builders: dict[str, _OutcomeBuilder] = {}
    for event in materialized:
        candidate_id = _text(event.get("candidate_id"))
        if not candidate_id:
            continue
        builder = builders.setdefault(candidate_id, _OutcomeBuilder(candidate_id=candidate_id))
        builder.apply(event)

    outcomes = tuple(sorted((builder.to_outcome() for builder in builders.values()), key=lambda item: item.first_sequence))
    closed_count = sum(1 for outcome in outcomes if outcome.status == OUTCOME_CLOSED)
    open_count = sum(1 for outcome in outcomes if outcome.status == OUTCOME_OPEN)
    rejected_count = sum(1 for outcome in outcomes if outcome.status == OUTCOME_REJECTED)
    invalid_count = sum(1 for outcome in outcomes if outcome.status == OUTCOME_INVALID)
    realized = sum(float(outcome.gross_pnl or 0.0) for outcome in outcomes if outcome.status == OUTCOME_CLOSED)
    return PaperOutcomeReductionReport(
        schema_version=PAPER_OUTCOME_REDUCER_SCHEMA_VERSION,
        source=PAPER_OUTCOME_REDUCER_SOURCE,
        status=PAPER_REDUCER_STATUS_REDUCED,
        journal_valid=True,
        reason_code="ok",
        reasons=(),
        event_count=len(materialized),
        candidate_count=len(outcomes),
        closed_count=closed_count,
        open_count=open_count,
        rejected_count=rejected_count,
        invalid_count=invalid_count,
        realized_gross_pnl=round(realized, 10),
        outcomes=outcomes,
        journal_validation=validation.to_payload(),
        metadata={
            "reducer": PAPER_OUTCOME_REDUCER_SOURCE,
            "journal_remains_source_of_truth": True,
            "does_not_append_journal": True,
            "does_not_call_external_execution": True,
            "does_not_compute_expectancy": True,
        },
    )


@dataclass
class _OutcomeBuilder:
    candidate_id: str
    strategy_id: str = ""
    symbol: str = ""
    entry_side: str = ""
    exit_side: str = ""
    quantity: float = 0.0
    entry_price: float | None = None
    exit_price: float | None = None
    first_sequence: int = 0
    latest_sequence: int = 0
    event_count: int = 0
    accepted: bool = False
    rejected: bool = False
    noted: bool = False
    blockers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def apply(self, event: Mapping[str, Any]) -> None:
        sequence = _int(event.get("sequence"))
        event_type = _text(event.get("event_type"))
        self.first_sequence = sequence if self.first_sequence == 0 else min(self.first_sequence, sequence)
        self.latest_sequence = max(self.latest_sequence, sequence)
        self.event_count += 1
        self.strategy_id = self.strategy_id or _text(event.get("strategy_id"))
        self.symbol = self.symbol or _text(event.get("symbol"))
        self.metadata["latest_event_type"] = event_type
        self.metadata["latest_mode"] = _text(event.get("mode")) or PAPER_MODE

        if event_type == PAPER_EVENT_CANDIDATE_ACCEPTED:
            self.accepted = True
        elif event_type == PAPER_EVENT_ENTRY_RECORDED:
            self._apply_entry(event)
        elif event_type == PAPER_EVENT_EXIT_RECORDED:
            self._apply_exit(event)
        elif event_type == PAPER_EVENT_REJECTED:
            self.rejected = True
            self._add_blocker(REJECTED_CANDIDATE_REASON)
        elif event_type == PAPER_EVENT_NOTE_RECORDED:
            self.noted = True
        else:
            self._add_blocker(UNHANDLED_EVENT_REASON)

    def _apply_entry(self, event: Mapping[str, Any]) -> None:
        if self.entry_price is not None:
            self._add_blocker(DUPLICATE_ENTRY_REASON)
            return
        self.entry_side = _text(event.get("side")).upper()
        self.quantity = _float(event.get("quantity"))
        self.entry_price = _optional_float(event.get("price"))

    def _apply_exit(self, event: Mapping[str, Any]) -> None:
        if self.entry_price is None:
            self._add_blocker(EXIT_WITHOUT_ENTRY_REASON)
        self.exit_side = _text(event.get("side")).upper()
        if self.quantity == 0.0:
            self.quantity = _float(event.get("quantity"))
        self.exit_price = _optional_float(event.get("price"))

    def to_outcome(self) -> PaperCandidateOutcome:
        status = self._status()
        blockers = _dedupe(self.blockers)
        gross_pnl = self._gross_pnl(status)
        return PaperCandidateOutcome(
            candidate_id=self.candidate_id,
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            status=status,
            entry_side=self.entry_side,
            exit_side=self.exit_side,
            quantity=self.quantity,
            entry_price=self.entry_price,
            exit_price=self.exit_price,
            gross_pnl=gross_pnl,
            first_sequence=self.first_sequence,
            latest_sequence=self.latest_sequence,
            event_count=self.event_count,
            blockers=blockers,
            metadata=dict(self.metadata),
        )

    def _status(self) -> str:
        blockers = _dedupe(self.blockers)
        if any(reason in blockers for reason in (EXIT_WITHOUT_ENTRY_REASON, DUPLICATE_ENTRY_REASON, UNHANDLED_EVENT_REASON)):
            return OUTCOME_INVALID
        if self.rejected:
            return OUTCOME_REJECTED
        if self.entry_price is not None and self.exit_price is not None:
            return OUTCOME_CLOSED
        if self.entry_price is not None:
            self._add_blocker(OPEN_POSITION_REASON)
            return OUTCOME_OPEN
        if self.noted and not self.accepted:
            self._add_blocker(NOTE_ONLY_REASON)
            return OUTCOME_NOTE_ONLY
        return OUTCOME_ACCEPTED

    def _gross_pnl(self, status: str) -> float | None:
        if status != OUTCOME_CLOSED or self.entry_price is None or self.exit_price is None:
            return None
        if self.entry_side == "SELL":
            return round((self.entry_price - self.exit_price) * self.quantity, 10)
        return round((self.exit_price - self.entry_price) * self.quantity, 10)

    def _add_blocker(self, reason: str) -> None:
        if reason not in self.blockers:
            self.blockers.append(reason)


def _blocked_report(validation: PaperTruthJournalValidation) -> PaperOutcomeReductionReport:
    return PaperOutcomeReductionReport(
        schema_version=PAPER_OUTCOME_REDUCER_SCHEMA_VERSION,
        source=PAPER_OUTCOME_REDUCER_SOURCE,
        status=PAPER_REDUCER_STATUS_BLOCKED,
        journal_valid=False,
        reason_code=INVALID_JOURNAL_REASON,
        reasons=tuple(validation.reasons) or (INVALID_JOURNAL_REASON,),
        event_count=validation.event_count,
        candidate_count=0,
        closed_count=0,
        open_count=0,
        rejected_count=0,
        invalid_count=0,
        realized_gross_pnl=0.0,
        outcomes=(),
        journal_validation=validation.to_payload(),
        metadata={
            "reducer": PAPER_OUTCOME_REDUCER_SOURCE,
            "journal_remains_source_of_truth": True,
            "blocked_before_reduction": True,
        },
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    if value in (None, "", "None"):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value or "").strip()}))


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "DUPLICATE_ENTRY_REASON",
    "EXIT_WITHOUT_ENTRY_REASON",
    "INVALID_JOURNAL_REASON",
    "NOTE_ONLY_REASON",
    "OPEN_POSITION_REASON",
    "OUTCOME_ACCEPTED",
    "OUTCOME_CLOSED",
    "OUTCOME_INVALID",
    "OUTCOME_NOTE_ONLY",
    "OUTCOME_OPEN",
    "OUTCOME_REJECTED",
    "PAPER_OUTCOME_REDUCER_SCHEMA_VERSION",
    "PAPER_OUTCOME_REDUCER_SOURCE",
    "PAPER_REDUCER_STATUS_BLOCKED",
    "PAPER_REDUCER_STATUS_REDUCED",
    "REJECTED_CANDIDATE_REASON",
    "PaperCandidateOutcome",
    "PaperOutcomeReductionReport",
    "reduce_paper_outcomes",
    "reduce_paper_outcomes_from_journal",
]
