from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple

@dataclass(frozen=True)
class Trade:
    trade_id: str
    timestamp: datetime
    symbol: str
    instrument: str
    instrument_token: int | None
    strike: int
    expiry: str
    side: str              # BUY / SELL
    entry_price: float
    stop_loss: float
    target: float
    qty: int
    capital_at_risk: float
    expected_slippage: float
    confidence: float
    strategy: str
    regime: str
    tier: str = "MAIN"
    day_type: str = "UNKNOWN"
    entry_condition: str | None = None   # e.g., BUY_ABOVE / SELL_BELOW
    entry_ref_price: float | None = None # original ask/ltp used before trigger
    opt_ltp: float | None = None
    opt_bid: float | None = None
    opt_ask: float | None = None
    quote_ok: bool = True
    trade_score: float | None = None
    trade_alignment: float | None = None
    trade_score_detail: dict | None = None
    model_type: str | None = None
    model_version: str | None = None
    shadow_model_version: str | None = None
    shadow_confidence: float | None = None
    alpha_confidence: float | None = None
    alpha_uncertainty: float | None = None
    size_mult: float = 1.0
    option_type: str | None = None
    underlying: str | None = None
    instrument_type: str | None = None
    right: str | None = None
    instrument_id: str | None = None
    qty_lots: int | None = None
    qty_units: int | None = None
    validity_sec: int | None = None
    tradable: bool = True
    tradable_reasons_blocking: list[str] = field(default_factory=list)
    source_flags: dict = field(default_factory=dict)
    stop_distance: float | None = None

    def __post_init__(self):
        if self.stop_distance is not None:
            return
        try:
            distance = abs(float(self.entry_price) - float(self.stop_loss))
        except (TypeError, ValueError):
            distance = None
        if distance is not None and distance > 0:
            object.__setattr__(self, "stop_distance", distance)


@dataclass
class TradeIntent:
    trace_id: str
    desk_id: str
    timestamp_epoch: float
    underlying: str
    instrument_type: str
    expiry: str | None
    strike: int | float | None
    right: str | None
    instrument_id: str | None
    side: str
    entry_type: str
    entry_price: float
    sl_price: float
    target_price: float
    qty_lots: int
    qty_units: int
    validity_sec: int
    tradable: bool = False
    tradable_reasons_blocking: list[str] = field(default_factory=list)
    source_flags: dict = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)

    def build_instrument_id(self) -> Optional[str]:
        return build_instrument_id(
            self.underlying,
            self.instrument_type,
            self.expiry,
            self.strike,
            self.right,
        )

    def validate_prices(self) -> Tuple[bool, str]:
        if self.entry_price is None or self.entry_price <= 0:
            return False, "invalid_entry_price"
        if self.sl_price is None or self.sl_price <= 0:
            return False, "invalid_stop_loss"
        if self.target_price is None or self.target_price <= 0:
            return False, "invalid_target"
        if self.side == "BUY":
            if self.sl_price >= self.entry_price:
                return False, "stop_above_entry"
            if self.target_price <= self.entry_price:
                return False, "target_below_entry"
        if self.side == "SELL":
            if self.sl_price <= self.entry_price:
                return False, "stop_below_entry"
            if self.target_price >= self.entry_price:
                return False, "target_above_entry"
        return True, "ok"

    def is_actionable(self) -> Tuple[bool, str]:
        if self.tradable is False:
            return False, "non_tradable"
        if not self.trace_id:
            return False, "missing_trace_id"
        if not self.desk_id:
            return False, "missing_desk_id"
        if self.side not in ("BUY", "SELL"):
            return False, "invalid_side"
        if self.entry_type not in ("LIMIT", "MARKET"):
            return False, "invalid_entry_type"
        if self.qty_lots <= 0:
            return False, "invalid_qty_lots"
        if self.qty_units <= 0:
            return False, "invalid_qty_units"
        if self.validity_sec <= 0:
            return False, "invalid_validity_sec"
        ok_identity, reason_identity = validate_trade_identity(
            self.underlying,
            self.instrument_type,
            self.expiry,
            self.strike,
            self.right,
        )
        if not ok_identity:
            return False, reason_identity
        current_id = self.instrument_id or self.build_instrument_id()
        if not current_id:
            return False, "missing_instrument_id"
        ok_price, reason_price = self.validate_prices()
        if not ok_price:
            return False, reason_price
        return True, "ok"


def build_instrument_id(
    underlying: str | None,
    instrument_type: str | None,
    expiry: str | None,
    strike: int | float | None,
    right: str | None,
) -> Optional[str]:
    if not underlying or not instrument_type:
        return None
    instrument_type = instrument_type.upper()
    if instrument_type == "OPT":
        if not expiry or strike is None or not right:
            return None
        return f"{underlying}|{expiry}|{strike}|{right}"
    if instrument_type == "FUT":
        if not expiry:
            return None
        return f"{underlying}|{expiry}|FUT"
    if instrument_type == "INDEX":
        return f"{underlying}|INDEX"
    return None


def validate_trade_identity(
    underlying: str | None,
    instrument_type: str | None,
    expiry: str | None,
    strike: int | float | None,
    right: str | None,
) -> Tuple[bool, str]:
    if not underlying:
        return False, "missing_underlying"
    if not instrument_type:
        return False, "missing_instrument_type"
    instrument_type = instrument_type.upper()
    if instrument_type == "OPT":
        if not expiry:
            return False, "missing_expiry"
        if strike is None:
            return False, "missing_strike"
        if right not in ("CE", "PE"):
            return False, "missing_right"
    if instrument_type == "FUT" and not expiry:
        return False, "missing_expiry"
    return True, "ok"
