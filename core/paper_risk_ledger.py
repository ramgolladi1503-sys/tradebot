"""Deterministic paper risk ledger reducer.

This module reduces explicit paper ledger events into a risk snapshot that can be
consumed by the read-only risk decision layer. It does not create orders,
simulate fills, mutate paper order state, write files, call brokers, or wire
runtime/dashboard behavior.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Iterable, Mapping

PAPER_RISK_LEDGER_SCHEMA_VERSION = 1

POSITION_OPENED = "POSITION_OPENED"
POSITION_CLOSED = "POSITION_CLOSED"
RISK_HALT_ACTIVATED = "RISK_HALT_ACTIVATED"
RISK_HALT_CLEARED = "RISK_HALT_CLEARED"

LEDGER_EVENT_TYPES: frozenset[str] = frozenset(
    {
        POSITION_OPENED,
        POSITION_CLOSED,
        RISK_HALT_ACTIVATED,
        RISK_HALT_CLEARED,
    }
)


class PaperRiskLedgerError(ValueError):
    """Raised when paper ledger input would create unsafe or inconsistent state."""


def _to_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    return None


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    return out if out == out else default


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _list_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


@dataclass(frozen=True)
class PaperRiskLedgerPosition:
    paper_order_id: str
    paper_intent_id: str
    symbol: str
    direction: str
    instrument_token: int
    tradingsymbol: str
    quantity: int
    entry_price: float
    entry_notional: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PaperRiskLedgerEvent:
    event_id: str
    event_type: str
    paper_order_id: str | None = None
    paper_intent_id: str | None = None
    symbol: str | None = None
    direction: str | None = None
    instrument_token: int | None = None
    tradingsymbol: str | None = None
    quantity: int = 0
    entry_price: float | None = None
    exit_price: float | None = None
    realized_pnl: float | None = None
    reason: str | None = None
    broker_order_action: bool = False
    live_order_action: bool = False
    is_order_action: bool = False
    append: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PaperRiskLedgerSnapshot:
    schema_version: int
    read_only: bool
    is_order_action: bool
    append: bool
    broker_order_action: bool
    live_order_action: bool
    risk_halt_active: bool
    daily_realized_pnl: float
    daily_trade_count: int
    open_position_count: int
    closed_position_count: int
    rejected_event_count: int
    current_exposure: float
    open_positions: tuple[PaperRiskLedgerPosition, ...]
    open_instrument_tokens: tuple[int, ...]
    open_tradingsymbols: tuple[str, ...]
    processed_event_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["open_positions"] = [position.to_dict() for position in self.open_positions]
        payload["open_instrument_tokens"] = list(self.open_instrument_tokens)
        payload["open_tradingsymbols"] = list(self.open_tradingsymbols)
        payload["processed_event_ids"] = list(self.processed_event_ids)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["metadata"] = dict(self.metadata)
        return payload


def _empty_snapshot() -> PaperRiskLedgerSnapshot:
    return PaperRiskLedgerSnapshot(
        schema_version=PAPER_RISK_LEDGER_SCHEMA_VERSION,
        read_only=True,
        is_order_action=False,
        append=False,
        broker_order_action=False,
        live_order_action=False,
        risk_halt_active=False,
        daily_realized_pnl=0.0,
        daily_trade_count=0,
        open_position_count=0,
        closed_position_count=0,
        rejected_event_count=0,
        current_exposure=0.0,
        open_positions=(),
        open_instrument_tokens=(),
        open_tradingsymbols=(),
        processed_event_ids=(),
        blockers=(),
        warnings=(),
        metadata={
            "ledger": "paper_risk_ledger_v1",
            "scope": "event_reducer_no_broker_calls_no_order_creation_no_persistence_no_runtime_wiring",
            "event_types": sorted(LEDGER_EVENT_TYPES),
        },
    )


def _normalize_event(event: Any) -> PaperRiskLedgerEvent:
    data = _to_mapping(event)
    if data is None:
        raise PaperRiskLedgerError("ledger_event_invalid")

    event_id = _text(data.get("event_id"))
    if event_id is None:
        raise PaperRiskLedgerError("ledger_event_id_missing")

    event_type = str(data.get("event_type") or "").strip().upper()
    if event_type not in LEDGER_EVENT_TYPES:
        raise PaperRiskLedgerError(f"unsupported_ledger_event_type:{event_type}")

    if _bool(data.get("broker_order_action"), default=False):
        raise PaperRiskLedgerError("ledger_event_broker_order_action_rejected")
    if _bool(data.get("live_order_action"), default=False):
        raise PaperRiskLedgerError("ledger_event_live_order_action_rejected")
    if _bool(data.get("is_order_action"), default=False):
        raise PaperRiskLedgerError("ledger_event_order_action_rejected")
    if _bool(data.get("append"), default=False):
        raise PaperRiskLedgerError("ledger_event_append_true_rejected")

    return PaperRiskLedgerEvent(
        event_id=event_id,
        event_type=event_type,
        paper_order_id=_text(data.get("paper_order_id")),
        paper_intent_id=_text(data.get("paper_intent_id")),
        symbol=_text(data.get("symbol")),
        direction=_text(data.get("direction")),
        instrument_token=_as_int(data.get("instrument_token"), default=0) or None,
        tradingsymbol=_text(data.get("tradingsymbol")),
        quantity=_as_int(data.get("quantity"), default=0),
        entry_price=_as_float(data.get("entry_price"), default=0.0) if data.get("entry_price") is not None else None,
        exit_price=_as_float(data.get("exit_price"), default=0.0) if data.get("exit_price") is not None else None,
        realized_pnl=_as_float(data.get("realized_pnl"), default=0.0) if data.get("realized_pnl") is not None else None,
        reason=_text(data.get("reason")),
        broker_order_action=False,
        live_order_action=False,
        is_order_action=False,
        append=False,
    )


def _position_from_open_event(event: PaperRiskLedgerEvent) -> PaperRiskLedgerPosition:
    blockers: list[str] = []
    if not event.paper_order_id:
        blockers.append("PAPER_ORDER_ID_MISSING")
    if not event.paper_intent_id:
        blockers.append("PAPER_INTENT_ID_MISSING")
    if not event.symbol:
        blockers.append("SYMBOL_MISSING")
    if not event.direction:
        blockers.append("DIRECTION_MISSING")
    if not event.instrument_token or event.instrument_token <= 0:
        blockers.append("INSTRUMENT_TOKEN_MISSING")
    if not event.tradingsymbol:
        blockers.append("TRADINGSYMBOL_MISSING")
    if event.quantity <= 0:
        blockers.append("QUANTITY_MISSING")
    if event.entry_price is None or event.entry_price <= 0.0:
        blockers.append("ENTRY_PRICE_MISSING")

    if blockers:
        raise PaperRiskLedgerError("position_open_event_invalid:" + ",".join(_dedupe(blockers)))

    entry_notional = round(float(event.quantity) * float(event.entry_price), 6)
    return PaperRiskLedgerPosition(
        paper_order_id=str(event.paper_order_id),
        paper_intent_id=str(event.paper_intent_id),
        symbol=str(event.symbol),
        direction=str(event.direction),
        instrument_token=int(event.instrument_token or 0),
        tradingsymbol=str(event.tradingsymbol),
        quantity=int(event.quantity),
        entry_price=round(float(event.entry_price), 6),
        entry_notional=entry_notional,
    )


def _realized_pnl(position: PaperRiskLedgerPosition, event: PaperRiskLedgerEvent) -> float:
    if event.realized_pnl is not None:
        return round(float(event.realized_pnl), 6)
    if event.exit_price is None or event.exit_price <= 0.0:
        raise PaperRiskLedgerError("position_close_exit_price_missing")
    # Current paper scope only models long option entries/exits. SELL/short PnL is
    # intentionally not inferred here because that would add unscoped strategy behavior.
    return round((float(event.exit_price) - float(position.entry_price)) * int(position.quantity), 6)


def reduce_paper_risk_ledger_events(events: Iterable[Any]) -> PaperRiskLedgerSnapshot:
    """Reduce ledger events into a deterministic, JSON-friendly risk snapshot."""

    snapshot = _empty_snapshot()
    open_positions: dict[str, PaperRiskLedgerPosition] = {}
    processed_ids: list[str] = []
    warnings: list[str] = []
    daily_realized_pnl = 0.0
    daily_trade_count = 0
    closed_position_count = 0
    rejected_event_count = 0
    risk_halt_active = False

    for raw_event in events:
        event = _normalize_event(raw_event)
        if event.event_id in set(processed_ids):
            raise PaperRiskLedgerError(f"duplicate_ledger_event_id:{event.event_id}")
        processed_ids.append(event.event_id)

        if event.event_type == RISK_HALT_ACTIVATED:
            risk_halt_active = True
            continue
        if event.event_type == RISK_HALT_CLEARED:
            risk_halt_active = False
            continue

        if event.event_type == POSITION_OPENED:
            position = _position_from_open_event(event)
            if position.paper_order_id in open_positions:
                raise PaperRiskLedgerError(f"duplicate_open_paper_order:{position.paper_order_id}")
            if any(existing.instrument_token == position.instrument_token for existing in open_positions.values()):
                raise PaperRiskLedgerError(f"duplicate_open_instrument_token:{position.instrument_token}")
            if any(existing.tradingsymbol == position.tradingsymbol for existing in open_positions.values()):
                raise PaperRiskLedgerError(f"duplicate_open_tradingsymbol:{position.tradingsymbol}")
            open_positions[position.paper_order_id] = position
            daily_trade_count += 1
            continue

        if event.event_type == POSITION_CLOSED:
            paper_order_id = _text(event.paper_order_id)
            if paper_order_id is None:
                raise PaperRiskLedgerError("position_close_paper_order_id_missing")
            position = open_positions.pop(paper_order_id, None)
            if position is None:
                raise PaperRiskLedgerError(f"position_close_unknown_paper_order:{paper_order_id}")
            close_qty = event.quantity or position.quantity
            if int(close_qty) != int(position.quantity):
                raise PaperRiskLedgerError("position_close_requires_full_quantity")
            daily_realized_pnl = round(daily_realized_pnl + _realized_pnl(position, event), 6)
            closed_position_count += 1
            continue

        rejected_event_count += 1
        warnings.append(f"UNHANDLED_LEDGER_EVENT:{event.event_type}")

    sorted_positions = tuple(sorted(open_positions.values(), key=lambda item: item.paper_order_id))
    current_exposure = round(sum(position.entry_notional for position in sorted_positions), 6)
    return replace(
        snapshot,
        risk_halt_active=risk_halt_active,
        daily_realized_pnl=round(float(daily_realized_pnl), 6),
        daily_trade_count=int(daily_trade_count),
        open_position_count=len(sorted_positions),
        closed_position_count=int(closed_position_count),
        rejected_event_count=int(rejected_event_count),
        current_exposure=current_exposure,
        open_positions=sorted_positions,
        open_instrument_tokens=tuple(sorted(position.instrument_token for position in sorted_positions)),
        open_tradingsymbols=tuple(sorted(position.tradingsymbol for position in sorted_positions)),
        processed_event_ids=tuple(processed_ids),
        warnings=_dedupe(warnings),
    )


def empty_paper_risk_ledger_snapshot() -> PaperRiskLedgerSnapshot:
    """Return an empty safe snapshot for risk-decision callers."""

    return _empty_snapshot()


__all__ = [
    "LEDGER_EVENT_TYPES",
    "PAPER_RISK_LEDGER_SCHEMA_VERSION",
    "POSITION_CLOSED",
    "POSITION_OPENED",
    "RISK_HALT_ACTIVATED",
    "RISK_HALT_CLEARED",
    "PaperRiskLedgerError",
    "PaperRiskLedgerEvent",
    "PaperRiskLedgerPosition",
    "PaperRiskLedgerSnapshot",
    "empty_paper_risk_ledger_snapshot",
    "reduce_paper_risk_ledger_events",
]
