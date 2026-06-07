from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any, Mapping


COST_SLIPPAGE_MODEL_SCHEMA_VERSION = 1

READY = "READY"
DEGRADED = "DEGRADED"
BLOCKED = "BLOCKED"

MISSING_BID_ASK = "MISSING_BID_ASK"
INVALID_RISK_PER_UNIT = "INVALID_RISK_PER_UNIT"
INVALID_DIRECTION = "INVALID_DIRECTION"
INVALID_INPUT = "INVALID_INPUT"

_SUPPORTED_DIRECTIONS = {"BUY", "LONG", "SELL", "SHORT"}


@dataclass(frozen=True)
class CostSlippageModelInput:
    entry_price: float | None = None
    exit_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    spread_pct: float | None = None
    lot_size: float | None = None
    quantity: float | None = None
    risk_per_unit: float | None = None
    brokerage: float | None = None
    taxes: float | None = None
    slippage_ticks: float | None = None
    tick_size: float | None = None
    side: str | None = None
    direction: str | None = None


@dataclass(frozen=True)
class CostSlippageModelResult:
    schema_version: int
    cost_model_status: str
    cost_model_blockers: tuple[str, ...]
    cost_model_warnings: tuple[str, ...]
    estimated_cost_abs: float
    estimated_cost_r: float | None
    spread_cost_abs: float
    slippage_cost_abs: float
    fee_cost_abs: float
    effective_entry: float | None
    effective_exit: float | None
    read_only: bool = True
    append: bool = False

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_allowed(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = COST_SLIPPAGE_MODEL_SCHEMA_VERSION
        payload["read_only"] = True
        payload["append"] = False
        payload["is_order_action"] = False
        payload["broker_api_called"] = False
        payload["live_order_allowed"] = False
        payload["live_order_action"] = False
        payload["broker_order_action"] = False
        return payload


def _float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    return number if isfinite(number) else None


def _mapping(input_model: Any) -> Mapping[str, Any]:
    if isinstance(input_model, Mapping):
        return input_model
    if hasattr(input_model, "__dict__"):
        return dict(vars(input_model))
    return {}


def _text(value: Any) -> str:
    return str(value or "").strip().upper()


def _direction(input_model: CostSlippageModelInput) -> str:
    raw = _text(input_model.direction or input_model.side or "BUY")
    if raw in {"BUY", "LONG"}:
        return "BUY"
    if raw in {"SELL", "SHORT"}:
        return "SELL"
    return raw


def _position_units(payload: Mapping[str, Any]) -> float:
    quantity = _float(payload.get("quantity"))
    lot_size = _float(payload.get("lot_size"))
    if quantity is not None and lot_size is not None:
        return max(quantity, 0.0) * max(lot_size, 0.0)
    if quantity is not None:
        return max(quantity, 0.0)
    if lot_size is not None:
        return max(lot_size, 0.0)
    return 1.0


def _side_reference_prices(
    *,
    direction: str,
    entry_price: float | None,
    exit_price: float | None,
    bid: float | None,
    ask: float | None,
    best_bid: float | None,
    best_ask: float | None,
    slippage_abs_unit: float,
) -> tuple[float | None, float | None]:
    if direction == "SELL":
        entry_ref_candidates = [value for value in (entry_price, bid, best_bid) if value is not None]
        exit_ref_candidates = [value for value in (exit_price, ask, best_ask) if value is not None]
        effective_entry = min(entry_ref_candidates) - slippage_abs_unit if entry_ref_candidates else None
        effective_exit = max(exit_ref_candidates) + slippage_abs_unit if exit_ref_candidates else None
        return effective_entry, effective_exit

    entry_ref_candidates = [value for value in (entry_price, ask, best_ask) if value is not None]
    exit_ref_candidates = [value for value in (exit_price, bid, best_bid) if value is not None]
    effective_entry = max(entry_ref_candidates) + slippage_abs_unit if entry_ref_candidates else None
    effective_exit = min(exit_ref_candidates) - slippage_abs_unit if exit_ref_candidates else None
    return effective_entry, effective_exit


def build_cost_slippage_model(input_model: Any) -> CostSlippageModelResult:
    payload = _mapping(input_model)
    entry_price = _float(payload.get("entry_price"))
    exit_price = _float(payload.get("exit_price"))
    bid = _float(payload.get("bid"))
    ask = _float(payload.get("ask"))
    best_bid = _float(payload.get("best_bid"))
    best_ask = _float(payload.get("best_ask"))
    spread = _float(payload.get("spread"))
    spread_pct = _float(payload.get("spread_pct"))
    lot_size = _float(payload.get("lot_size"))
    quantity = _float(payload.get("quantity"))
    risk_per_unit = _float(payload.get("risk_per_unit"))
    brokerage = max(_float(payload.get("brokerage")) or 0.0, 0.0)
    taxes = max(_float(payload.get("taxes")) or 0.0, 0.0)
    slippage_ticks = max(_float(payload.get("slippage_ticks")) or 0.0, 0.0)
    tick_size = max(_float(payload.get("tick_size")) or 0.0, 0.0)
    direction = _direction(CostSlippageModelInput(side=payload.get("side"), direction=payload.get("direction")))

    blockers: list[str] = []
    warnings: list[str] = []

    if direction not in _SUPPORTED_DIRECTIONS:
        return CostSlippageModelResult(
            schema_version=COST_SLIPPAGE_MODEL_SCHEMA_VERSION,
            cost_model_status=BLOCKED,
            cost_model_blockers=(INVALID_DIRECTION,),
            cost_model_warnings=(),
            estimated_cost_abs=0.0,
            estimated_cost_r=None,
            spread_cost_abs=0.0,
            slippage_cost_abs=0.0,
            fee_cost_abs=0.0,
            effective_entry=entry_price,
            effective_exit=exit_price,
        )

    if bid is None or ask is None:
        blockers.append(MISSING_BID_ASK)
        warnings.append("missing_bid_ask_degraded_cost_model")

    if risk_per_unit is None or risk_per_unit <= 0:
        blockers.append(INVALID_RISK_PER_UNIT)

    units = _position_units(payload)
    spread_value = spread
    if spread_value is None and bid is not None and ask is not None:
        spread_value = ask - bid
    if spread_value is None and spread_pct is not None:
        mid = None
        if entry_price is not None and exit_price is not None:
            mid = (entry_price + exit_price) / 2.0
        elif entry_price is not None:
            mid = entry_price
        elif exit_price is not None:
            mid = exit_price
        if mid is not None:
            spread_value = max(0.0, mid * (spread_pct / 100.0))
    spread_value = max(spread_value or 0.0, 0.0)
    spread_cost_abs = round(spread_value * units, 6)
    slippage_per_side_abs = slippage_ticks * tick_size
    slippage_cost_abs = round(slippage_per_side_abs * units * 2.0, 6)
    fee_cost_abs = round(brokerage + taxes, 6)
    estimated_cost_abs = round(spread_cost_abs + slippage_cost_abs + fee_cost_abs, 6)

    effective_entry, effective_exit = _side_reference_prices(
        direction=direction,
        entry_price=entry_price,
        exit_price=exit_price,
        bid=bid,
        ask=ask,
        best_bid=best_bid,
        best_ask=best_ask,
        slippage_abs_unit=slippage_per_side_abs,
    )

    estimated_cost_r = None
    if risk_per_unit and risk_per_unit > 0:
        estimated_cost_r = round(estimated_cost_abs / risk_per_unit, 6)

    status = READY
    if blockers:
        status = DEGRADED if MISSING_BID_ASK in blockers and len(blockers) == 1 else BLOCKED

    return CostSlippageModelResult(
        schema_version=COST_SLIPPAGE_MODEL_SCHEMA_VERSION,
        cost_model_status=status,
        cost_model_blockers=tuple(blockers),
        cost_model_warnings=tuple(warnings),
        estimated_cost_abs=estimated_cost_abs,
        estimated_cost_r=estimated_cost_r,
        spread_cost_abs=spread_cost_abs,
        slippage_cost_abs=slippage_cost_abs,
        fee_cost_abs=fee_cost_abs,
        effective_entry=effective_entry,
        effective_exit=effective_exit,
    )


__all__ = [
    "BLOCKED",
    "COST_SLIPPAGE_MODEL_SCHEMA_VERSION",
    "CostSlippageModelInput",
    "CostSlippageModelResult",
    "DEGRADED",
    "INVALID_DIRECTION",
    "INVALID_INPUT",
    "INVALID_RISK_PER_UNIT",
    "MISSING_BID_ASK",
    "READY",
    "build_cost_slippage_model",
]
