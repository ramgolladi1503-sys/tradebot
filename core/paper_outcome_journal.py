"""Paper outcome journal contract.

This module is the narrow EDGE-02 contract layer between paper candidate/order
outcomes and the existing offline family-learning journal. It does not create
orders, mutate strategies, call brokers, or infer profitability. Its job is to
fail closed when a paper outcome is missing terminal truth.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.edge_setup_identity import EdgeSetupIdentityError, enrich_record_with_edge_setup_identity
from core.offline_family_learning import record_family_outcome

PAPER_OUTCOME_JOURNAL_SCHEMA_VERSION = 1

EXECUTED = "executed"
REJECTED_SAVED_LOSS = "rejected-saved-loss"
REJECTED_MISSED_WIN = "rejected-missed-win"
EXPIRED_NO_MOVE = "expired-no-move"
STOPPED = "stopped"
TARGET_HIT = "target-hit"
TIMED_EXIT = "timed-exit"

ALLOWED_TERMINAL_OUTCOMES: frozenset[str] = frozenset(
    {
        EXECUTED,
        REJECTED_SAVED_LOSS,
        REJECTED_MISSED_WIN,
        EXPIRED_NO_MOVE,
        STOPPED,
        TARGET_HIT,
        TIMED_EXIT,
    }
)

_SETUP_IDENTITY_TRIGGER_FIELDS: frozenset[str] = frozenset(
    {"setup_id", "entry_rule_id", "exit_rule_id", "cost_model_version"}
)


class PaperOutcomeJournalError(ValueError):
    """Raised when paper outcome journal input is invalid."""


@dataclass(frozen=True)
class PaperOutcomeJournalRecord:
    schema_version: int
    timestamp: str
    candidate_id: str
    paper_intent_id: str | None
    strategy_family: str
    regime: str
    direction_family: str
    terminal_status: str
    candidate_class: str | None
    selector_outcome: str | None
    signal_score: float | None
    execution_score: float | None
    priority_score: float | None
    final_score: float | None
    selection_probability: float | None
    simulation_status: str
    fill_status: str | None
    mfe: float | None
    mae: float | None
    simulated_pnl: float | None
    slippage_adjusted_pnl: float | None
    slippage_cost: float | None
    exit_reason: str
    would_have_worked: bool
    rejection_saved_loss: bool
    rejection_missed_win: bool
    realized_r_multiple: float | None
    stop_hit_before_target: bool
    risk_plan_respected: bool
    mode: str
    source: str
    reason: str
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
        payload["metadata"] = dict(self.metadata)
        payload["is_order_action"] = self.is_order_action
        payload["broker_api_called"] = self.broker_api_called
        payload["live_order_action"] = self.live_order_action
        payload["broker_order_action"] = self.broker_order_action
        return payload


@dataclass(frozen=True)
class PaperOutcomeJournalIntegrityReport:
    schema_version: int
    checked_records: int
    valid_records: int
    invalid_records: int
    terminal_status_counts: dict[str, int]
    invalid_reasons: tuple[str, ...]
    read_only: bool
    source: str

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def passed(self) -> bool:
        return self.invalid_records == 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["invalid_reasons"] = list(self.invalid_reasons)
        payload["passed"] = self.passed
        payload["is_order_action"] = self.is_order_action
        payload["broker_api_called"] = self.broker_api_called
        return payload


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    raise PaperOutcomeJournalError("paper_outcome_mapping_required")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, *, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _slug(value: Any, *, default: str = "unknown") -> str:
    text = _text(value).lower().replace("_", "-").replace(" ", "-")
    return text or default


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _float_or_none(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        number = float(value)
    except Exception:
        return None
    return number if number == number else None


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _direction(value: Any) -> str:
    text = _slug(value)
    if text in {"buy-call", "call", "ce", "bull", "bullish", "long-ce", "up"}:
        return "bullish"
    if text in {"buy-put", "put", "pe", "bear", "bearish", "long-pe", "down"}:
        return "bearish"
    return text


def normalize_terminal_outcome(value: Any) -> str:
    text = _slug(value, default="")
    aliases = {
        "sim-executed": EXECUTED,
        "filled": EXECUTED,
        "sim-partial-fill": EXECUTED,
        "rejected-saved-loss": REJECTED_SAVED_LOSS,
        "saved-loss": REJECTED_SAVED_LOSS,
        "rejected-missed-win": REJECTED_MISSED_WIN,
        "missed-win": REJECTED_MISSED_WIN,
        "expired": EXPIRED_NO_MOVE,
        "expired-no-move": EXPIRED_NO_MOVE,
        "no-move": EXPIRED_NO_MOVE,
        "stop-hit": STOPPED,
        "sl-hit": STOPPED,
        "stopped": STOPPED,
        "target": TARGET_HIT,
        "target-hit": TARGET_HIT,
        "profit-target": TARGET_HIT,
        "timed-exit": TIMED_EXIT,
        "time-exit": TIMED_EXIT,
    }
    normalized = aliases.get(text, text)
    if normalized not in ALLOWED_TERMINAL_OUTCOMES:
        raise PaperOutcomeJournalError(f"paper_terminal_outcome_invalid:{text or 'missing'}")
    return normalized


def _require_text(record: Mapping[str, Any], *keys: str, field: str) -> str:
    for key in keys:
        text = _text(record.get(key))
        if text:
            return text
    raise PaperOutcomeJournalError(f"paper_outcome_required_field_missing:{field}")


def _slippage_adjusted_pnl(record: Mapping[str, Any]) -> float | None:
    explicit = _float_or_none(record.get("slippage_adjusted_pnl"))
    if explicit is not None:
        return explicit
    pnl = _float_or_none(record.get("simulated_pnl") or record.get("realized_pnl") or record.get("pnl"))
    if pnl is None:
        return None
    slippage_cost = abs(_float_or_none(record.get("slippage_cost")) or 0.0)
    return round(float(pnl - slippage_cost), 6)


def _has_setup_identity_input(record: Mapping[str, Any]) -> bool:
    return any(_text(record.get(field)) for field in _SETUP_IDENTITY_TRIGGER_FIELDS)


def _with_optional_setup_identity(payload: dict[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    if not _has_setup_identity_input(source):
        return payload
    candidate = dict(payload)
    for field in (
        "setup_id",
        "entry_rule_id",
        "exit_rule_id",
        "cost_model_version",
        "regime_key",
        "score_bucket",
    ):
        if field in source:
            candidate[field] = source.get(field)
    try:
        enriched = enrich_record_with_edge_setup_identity(candidate)
    except EdgeSetupIdentityError as exc:
        raise PaperOutcomeJournalError(f"paper_setup_identity_invalid:{exc}") from exc
    for field in (
        "setup_id",
        "regime_key",
        "entry_rule_id",
        "exit_rule_id",
        "cost_model_version",
        "score_bucket",
    ):
        payload[field] = enriched[field]
    metadata = dict(payload.get("metadata") or {})
    metadata["edge_setup_identity"] = dict(enriched.get("metadata", {}).get("edge_setup_identity") or {})
    payload["metadata"] = metadata
    return payload


def build_paper_outcome_journal_record(outcome: Any) -> PaperOutcomeJournalRecord:
    """Normalize one terminal paper outcome into family_outcomes.jsonl shape."""

    row = _as_mapping(outcome)
    terminal_status = normalize_terminal_outcome(
        row.get("terminal_status")
        or row.get("candidate_terminal_status")
        or row.get("exit_reason")
        or row.get("simulation_status")
    )
    candidate_id = _require_text(row, "candidate_id", "paper_candidate_id", "candidate_key", field="candidate_id")
    strategy_family = _slug(
        _require_text(row, "strategy_family", "family", "strategy", "strategy_name", field="strategy_family")
    )
    direction_family = _direction(
        _require_text(row, "direction_family", "direction", "side", "signal_direction", field="direction_family")
    )
    timestamp = _text(row.get("timestamp") or row.get("ts"), default=_utc_now())
    exit_reason = _slug(row.get("exit_reason") or terminal_status, default=terminal_status).upper()
    simulation_status = _slug(row.get("simulation_status") or terminal_status).upper()
    rejection_saved_loss = terminal_status == REJECTED_SAVED_LOSS or _bool(row.get("rejection_saved_loss"))
    rejection_missed_win = terminal_status == REJECTED_MISSED_WIN or _bool(row.get("rejection_missed_win"))

    return PaperOutcomeJournalRecord(
        schema_version=PAPER_OUTCOME_JOURNAL_SCHEMA_VERSION,
        timestamp=timestamp,
        candidate_id=candidate_id,
        paper_intent_id=_optional_text(row.get("paper_intent_id")),
        strategy_family=strategy_family,
        regime=_slug(row.get("regime") or row.get("market_regime") or row.get("regime_day")),
        direction_family=direction_family,
        terminal_status=terminal_status,
        candidate_class=_optional_text(row.get("candidate_class")),
        selector_outcome=_optional_text(row.get("selector_outcome")),
        signal_score=_float_or_none(row.get("signal_score")),
        execution_score=_float_or_none(row.get("execution_score")),
        priority_score=_float_or_none(row.get("priority_score")),
        final_score=_float_or_none(row.get("final_score") or row.get("score") or row.get("confidence")),
        selection_probability=_float_or_none(row.get("selection_probability")),
        simulation_status=simulation_status,
        fill_status=_optional_text(row.get("fill_status") or row.get("simulation_fill_status")),
        mfe=_float_or_none(row.get("mfe")),
        mae=_float_or_none(row.get("mae")),
        simulated_pnl=_float_or_none(row.get("simulated_pnl") or row.get("realized_pnl") or row.get("pnl")),
        slippage_adjusted_pnl=_slippage_adjusted_pnl(row),
        slippage_cost=_float_or_none(row.get("slippage_cost")),
        exit_reason=exit_reason,
        would_have_worked=_bool(row.get("would_have_worked")),
        rejection_saved_loss=rejection_saved_loss,
        rejection_missed_win=rejection_missed_win,
        realized_r_multiple=_float_or_none(row.get("realized_r_multiple") or row.get("r_multiple")),
        stop_hit_before_target=terminal_status == STOPPED or _bool(row.get("stop_hit_before_target")),
        risk_plan_respected=_bool(row.get("risk_plan_respected"), default=True),
        mode=_text(row.get("mode") or row.get("execution_mode"), default="PAPER").upper(),
        source=_text(row.get("source"), default="paper_outcome_journal_contract"),
        reason=_text(row.get("reason") or row.get("terminal_reason"), default=terminal_status),
        metadata={
            "contract": "paper_outcome_journal_v1",
            "source_of_truth": "family_outcomes_jsonl",
            "read_only_normalization": True,
            "allowed_terminal_outcomes": sorted(ALLOWED_TERMINAL_OUTCOMES),
        },
    )


def record_paper_outcome(
    outcome: Any,
    *,
    records_path: str | Path | None = None,
    state_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate and append one terminal paper outcome to family_outcomes.jsonl."""

    source = _as_mapping(outcome)
    record = build_paper_outcome_journal_record(source)
    payload = _with_optional_setup_identity(record.to_dict(), source)
    return record_family_outcome(payload, records_path=records_path, state_path=state_path)


def validate_paper_outcome_records(records: Iterable[dict[str, Any]]) -> PaperOutcomeJournalIntegrityReport:
    invalid_reasons: list[str] = []
    terminal_counts: dict[str, int] = {}
    checked = 0
    valid = 0
    for raw in records or []:
        checked += 1
        try:
            record = build_paper_outcome_journal_record(raw)
            _with_optional_setup_identity(record.to_dict(), raw)
        except PaperOutcomeJournalError as exc:
            invalid_reasons.append(str(exc))
            continue
        terminal_counts[record.terminal_status] = int(terminal_counts.get(record.terminal_status, 0)) + 1
        valid += 1
    return PaperOutcomeJournalIntegrityReport(
        schema_version=PAPER_OUTCOME_JOURNAL_SCHEMA_VERSION,
        checked_records=checked,
        valid_records=valid,
        invalid_records=checked - valid,
        terminal_status_counts=dict(sorted(terminal_counts.items())),
        invalid_reasons=tuple(invalid_reasons),
        read_only=True,
        source="paper_outcome_journal_contract",
    )


__all__ = [
    "ALLOWED_TERMINAL_OUTCOMES",
    "EXECUTED",
    "EXPIRED_NO_MOVE",
    "PAPER_OUTCOME_JOURNAL_SCHEMA_VERSION",
    "PaperOutcomeJournalError",
    "PaperOutcomeJournalIntegrityReport",
    "PaperOutcomeJournalRecord",
    "REJECTED_MISSED_WIN",
    "REJECTED_SAVED_LOSS",
    "STOPPED",
    "TARGET_HIT",
    "TIMED_EXIT",
    "build_paper_outcome_journal_record",
    "normalize_terminal_outcome",
    "record_paper_outcome",
    "validate_paper_outcome_records",
]
