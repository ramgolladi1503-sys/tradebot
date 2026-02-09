from dataclasses import dataclass
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
