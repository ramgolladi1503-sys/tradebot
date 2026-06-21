"""Paper exit outcome truth contract.

This module converts closed PAPER position/exit facts into journal-ready outcome
records. It does not monitor positions, run a strategy, transition live orders,
or call brokers. It only validates exit truth and appends through the existing
paper outcome journal contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from core.paper_outcome_journal import record_paper_outcome

PAPER_EXIT_OUTCOME_SCHEMA_VERSION = 1

TARGET_HIT = "target-hit"
STOPPED = "stopped"
TIMED_EXIT = "timed-exit"

ALLOWED_EXIT_OUTCOMES: frozenset[str] = frozenset({TARGET_HIT, STOPPED, TIMED_EXIT})


class PaperExitOutcomeError(ValueError):
    """Raised when paper exit outcome truth is invalid."""


@dataclass(frozen=True)
class PaperExitOutcomeRecord:
    schema_version: int
    candidate_id: str
    paper_intent_id: str | None
    strategy_family: str
    regime: str
    direction_family: str
    terminal_status: str
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    slippage_cost: float
    slippage_adjusted_pnl: float
    risk_per_unit: float | None
    realized_r_multiple: float | None
    exit_reason: str
    mode: str
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
        payload["simulated_pnl"] = self.gross_pnl
        payload["final_score"] = self.metadata.get("final_score")
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
    raise PaperExitOutcomeError("paper_exit_mapping_required")


def _text(value: Any, *, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _slug(value: Any, *, default: str = "unknown") -> str:
    text = _text(value).lower().replace("_", "-").replace(" ", "-")
    return text or default


def _float_required(row: Mapping[str, Any], *keys: str, field: str) -> float:
    for key in keys:
        try:
            if row.get(key) in (None, "", "None"):
                continue
            number = float(row.get(key))
        except Exception:
            continue
        if number == number:
            return number
    raise PaperExitOutcomeError(f"paper_exit_required_numeric_field_blank:{field}")


def _float_optional(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        number = float(value)
    except Exception:
        return None
    return number if number == number else None


def _required_text(row: Mapping[str, Any], *keys: str, field: str) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    raise PaperExitOutcomeError(f"paper_exit_required_text_field_blank:{field}")


def _direction(value: Any) -> str:
    text = _slug(value)
    if text in {"buy-call", "call", "ce", "bull", "bullish", "long-ce", "up", "buy"}:
        return "bullish"
    if text in {"buy-put", "put", "pe", "bear", "bearish", "long-pe", "down", "sell"}:
        return "bearish"
    return text


def normalize_exit_outcome(value: Any) -> str:
    text = _slug(value, default="")
    aliases = {
        "target": TARGET_HIT,
        "profit-target": TARGET_HIT,
        "target-hit": TARGET_HIT,
        "stop": STOPPED,
        "stop-hit": STOPPED,
        "stoploss-hit": STOPPED,
        "sl-hit": STOPPED,
        "stopped": STOPPED,
        "time-exit": TIMED_EXIT,
        "timed-exit": TIMED_EXIT,
        "session-close": TIMED_EXIT,
        "eod-exit": TIMED_EXIT,
    }
    normalized = aliases.get(text, text)
    if normalized not in ALLOWED_EXIT_OUTCOMES:
        raise PaperExitOutcomeError(f"paper_exit_outcome_invalid:{text or 'blank'}")
    return normalized


def _pnl(entry_price: float, exit_price: float, quantity: float, direction: str) -> float:
    direction_text = _direction(direction)
    if direction_text == "bearish":
        return round(float(entry_price - exit_price) * float(quantity), 6)
    return round(float(exit_price - entry_price) * float(quantity), 6)


def _risk_per_unit(row: Mapping[str, Any], entry_price: float) -> float | None:
    explicit = _float_optional(row.get("risk_per_unit"))
    if explicit is not None and explicit > 0:
        return explicit
    stop_price = _float_optional(row.get("stop_price") or row.get("stop_loss") or row.get("stop"))
    if stop_price is None:
        return None
    risk = abs(float(entry_price) - float(stop_price))
    return round(risk, 6) if risk > 0 else None


def _realized_r(gross_pnl: float, quantity: float, risk_per_unit: float | None) -> float | None:
    if risk_per_unit is None or risk_per_unit <= 0 or quantity <= 0:
        return None
    risk_total = float(risk_per_unit) * float(quantity)
    if risk_total <= 0:
        return None
    return round(float(gross_pnl) / risk_total, 6)


def build_paper_exit_outcome(exit_event: Any) -> PaperExitOutcomeRecord:
    row = _mapping(exit_event)
    terminal_status = normalize_exit_outcome(
        row.get("terminal_status") or row.get("exit_outcome") or row.get("exit_reason")
    )
    candidate_id = _required_text(row, "candidate_id", "trade_id", "paper_candidate_id", field="candidate")
    strategy_family = _slug(
        _required_text(row, "strategy_family", "family", "strategy", "strategy_name", field="strategy_family")
    )
    direction_family = _direction(
        _required_text(row, "direction_family", "direction", "side", "signal_direction", field="direction_family")
    )
    entry_price = _float_required(row, "entry_price", "entry", field="entry_price")
    exit_price = _float_required(row, "exit_price", "exit", "last_price", field="exit_price")
    quantity = _float_required(row, "quantity", "qty", "filled_qty", field="quantity")
    if quantity <= 0:
        raise PaperExitOutcomeError("paper_exit_quantity_must_be_positive")
    gross_pnl = _pnl(entry_price, exit_price, quantity, direction_family)
    slippage_cost = abs(_float_optional(row.get("slippage_cost")) or 0.0)
    slippage_adjusted_pnl = round(float(gross_pnl) - slippage_cost, 6)
    risk_unit = _risk_per_unit(row, entry_price)
    realized_r = _float_optional(row.get("realized_r_multiple") or row.get("r_multiple"))
    if realized_r is None:
        realized_r = _realized_r(gross_pnl, quantity, risk_unit)

    return PaperExitOutcomeRecord(
        schema_version=PAPER_EXIT_OUTCOME_SCHEMA_VERSION,
        candidate_id=candidate_id,
        paper_intent_id=_optional_text(row.get("paper_intent_id")),
        strategy_family=strategy_family,
        regime=_slug(row.get("regime") or row.get("market_regime") or row.get("regime_day")),
        direction_family=direction_family,
        terminal_status=terminal_status,
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        gross_pnl=gross_pnl,
        slippage_cost=slippage_cost,
        slippage_adjusted_pnl=slippage_adjusted_pnl,
        risk_per_unit=risk_unit,
        realized_r_multiple=realized_r,
        exit_reason=terminal_status,
        mode="PAPER",
        source="paper_exit_outcome_truth",
        metadata={
            "contract": "paper_exit_outcome_v1",
            "source_of_truth": "family_outcomes_jsonl",
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": quantity,
            "final_score": _float_optional(row.get("final_score") or row.get("score") or row.get("confidence")),
            "exit_outcome_truth": True,
        },
    )

def record_paper_exit_outcome(
    exit_event: Any,
    *,
    records_path: str | Path | None = None,
    state_path: str | Path | None = None,
) -> dict[str, Any]:
    record = build_paper_exit_outcome(exit_event)

    try:
        if "OPENING_DRIVE_CONT" in str(record.strategy_family).upper():
            from core.htf_paper_telemetry import log_htf_opening_drive_paper_exit
            log_htf_opening_drive_paper_exit(record.to_dict())
    except Exception as e:
        import logging
        logging.getLogger("htf_telemetry").warning("Failed to log paper exit: %s", e)

    return record_paper_outcome(record.to_dict(), records_path=records_path, state_path=state_path)


__all__ = [
    "ALLOWED_EXIT_OUTCOMES",
    "PAPER_EXIT_OUTCOME_SCHEMA_VERSION",
    "PaperExitOutcomeError",
    "PaperExitOutcomeRecord",
    "STOPPED",
    "TARGET_HIT",
    "TIMED_EXIT",
    "build_paper_exit_outcome",
    "normalize_exit_outcome",
    "record_paper_exit_outcome",
]
