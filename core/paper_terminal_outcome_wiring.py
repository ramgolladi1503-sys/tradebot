"""Terminal paper-order outcome wiring.

This module connects already-terminal paper-order records to the EDGE-02
paper outcome journal contract. It does not transition orders, simulate fills,
call brokers, mutate strategies, change scoring, or wire dashboard/runtime loops.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from core.paper_order_state_machine import CANCELLED, EXPIRED, FILLED, REJECTED, TERMINAL_STATES
from core.paper_outcome_journal import record_paper_outcome

PAPER_TERMINAL_OUTCOME_WIRING_SCHEMA_VERSION = 1

_ORDER_STATE_TO_TERMINAL_STATUS = {
    FILLED: "executed",
    REJECTED: "rejected-saved-loss",
    EXPIRED: "expired-no-move",
    CANCELLED: "timed-exit",
}


class PaperTerminalOutcomeWiringError(ValueError):
    """Raised when terminal paper outcome wiring input is invalid."""


@dataclass(frozen=True)
class TerminalPaperOutcomeDraft:
    schema_version: int
    candidate_id: str
    paper_intent_id: str | None
    paper_order_id: str | None
    strategy_family: str
    regime: str
    direction_family: str
    terminal_status: str
    terminal_order_state: str
    terminal_reason: str
    quantity: int | None
    entry_price: float | None
    exit_price: float | None
    simulated_pnl: float | None
    slippage_cost: float | None
    slippage_adjusted_pnl: float | None
    realized_r_multiple: float | None
    final_score: float | None
    source: str
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
        payload["is_order_action"] = self.is_order_action
        payload["broker_api_called"] = self.broker_api_called
        payload["live_order_action"] = self.live_order_action
        payload["broker_order_action"] = self.broker_order_action
        payload["metadata"] = dict(self.metadata)
        return payload


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    raise PaperTerminalOutcomeWiringError("terminal_paper_order_mapping_required")


def _text(value: Any, *, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _slug(value: Any, *, default: str = "unknown") -> str:
    text = _text(value).lower().replace("_", "-").replace(" ", "-")
    return text or default


def _float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        number = float(value)
    except Exception:
        return None
    return number if number == number else None


def _int(value: Any) -> int | None:
    try:
        if value in (None, "", "None"):
            return None
        return int(value)
    except Exception:
        return None


def _required_text(row: Mapping[str, Any], *keys: str, field: str) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    raise PaperTerminalOutcomeWiringError(f"terminal_outcome_field_required:{field}")


def _last_transition_reason(row: Mapping[str, Any]) -> str:
    transitions = row.get("transitions")
    if isinstance(transitions, list) and transitions:
        last = transitions[-1]
        if isinstance(last, Mapping):
            reason = _text(last.get("reason"))
            if reason:
                return reason
    return _text(row.get("terminal_reason") or row.get("reason"), default="paper_order_terminal")


def _terminal_status_for_state(state: str, row: Mapping[str, Any]) -> str:
    explicit = _text(row.get("terminal_status") or row.get("candidate_terminal_status"))
    if explicit:
        return explicit
    return _ORDER_STATE_TO_TERMINAL_STATUS.get(state, "")


def _slippage_adjusted_pnl(row: Mapping[str, Any]) -> float | None:
    explicit = _float(row.get("slippage_adjusted_pnl"))
    if explicit is not None:
        return explicit
    pnl = _float(row.get("simulated_pnl") or row.get("realized_pnl") or row.get("pnl"))
    if pnl is None:
        return None
    cost = abs(_float(row.get("slippage_cost")) or 0.0)
    return round(float(pnl - cost), 6)


def build_terminal_paper_outcome(order: Any, *, defaults: Mapping[str, Any] | None = None) -> TerminalPaperOutcomeDraft:
    """Build one journal-ready outcome from a terminal paper-order record."""

    row = dict(defaults or {})
    row.update(dict(_mapping(order)))
    state = _text(row.get("state")).upper()
    if state not in TERMINAL_STATES:
        raise PaperTerminalOutcomeWiringError(f"paper_order_not_terminal:{state or 'blank'}")

    terminal_status = _terminal_status_for_state(state, row)
    if not terminal_status:
        raise PaperTerminalOutcomeWiringError(f"paper_order_terminal_status_unmapped:{state}")

    paper_intent_id = _optional_text(row.get("paper_intent_id"))
    paper_order_id = _optional_text(row.get("paper_order_id"))
    candidate_id = _optional_text(row.get("candidate_id") or row.get("paper_candidate_id") or paper_intent_id or paper_order_id)
    if candidate_id is None:
        raise PaperTerminalOutcomeWiringError("terminal_outcome_field_required:candidate")

    strategy_family = _slug(_required_text(row, "strategy_family", "family", "strategy", "strategy_name", field="strategy_family"))
    direction_family = _required_text(row, "direction_family", "direction", "side", "signal_direction", field="direction_family")

    return TerminalPaperOutcomeDraft(
        schema_version=PAPER_TERMINAL_OUTCOME_WIRING_SCHEMA_VERSION,
        candidate_id=candidate_id,
        paper_intent_id=paper_intent_id,
        paper_order_id=paper_order_id,
        strategy_family=strategy_family,
        regime=_slug(row.get("regime") or row.get("market_regime") or row.get("regime_day")),
        direction_family=direction_family,
        terminal_status=terminal_status,
        terminal_order_state=state,
        terminal_reason=_last_transition_reason(row),
        quantity=_int(row.get("quantity")),
        entry_price=_float(row.get("entry_price")),
        exit_price=_float(row.get("exit_price") or row.get("fill_price") or row.get("last_price")),
        simulated_pnl=_float(row.get("simulated_pnl") or row.get("realized_pnl") or row.get("pnl")),
        slippage_cost=_float(row.get("slippage_cost")),
        slippage_adjusted_pnl=_slippage_adjusted_pnl(row),
        realized_r_multiple=_float(row.get("realized_r_multiple") or row.get("r_multiple")),
        final_score=_float(row.get("final_score") or row.get("score") or row.get("confidence")),
        source="paper_terminal_outcome_wiring",
        metadata={
            "contract": "paper_terminal_outcome_wiring_v1",
            "source_of_truth": "family_outcomes_jsonl",
            "input_order_state": state,
            "runtime_wiring": False,
        },
    )


def record_terminal_paper_outcome(
    order: Any,
    *,
    defaults: Mapping[str, Any] | None = None,
    records_path: str | Path | None = None,
    state_path: str | Path | None = None,
) -> dict[str, Any]:
    """Append a terminal paper-order outcome through the EDGE-02 journal contract."""

    draft = build_terminal_paper_outcome(order, defaults=defaults)
    return record_paper_outcome(draft.to_dict(), records_path=records_path, state_path=state_path)


__all__ = [
    "PAPER_TERMINAL_OUTCOME_WIRING_SCHEMA_VERSION",
    "PaperTerminalOutcomeWiringError",
    "TerminalPaperOutcomeDraft",
    "build_terminal_paper_outcome",
    "record_terminal_paper_outcome",
]
