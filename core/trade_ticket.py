from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Tuple, Optional

from core.time_utils import now_ist
from core.trade_schema import build_instrument_id, validate_trade_identity


@dataclass
class TradeTicket:
    trace_id: str
    timestamp_epoch: float
    timestamp_ist: str
    desk_id: str
    underlying: str
    instrument_type: str
    expiry: str | None
    strike: float | int | None
    right: str | None
    instrument_id: str | None
    side: str
    entry_type: str
    entry_price: float
    sl_price: float
    tgt_price: float
    qty_lots: int
    qty_units: int
    validity_sec: int
    tradable: bool = True
    tradable_reasons_blocking: List[str] = field(default_factory=list)
    source_flags: dict = field(default_factory=dict)
    reason_codes: List[str] = field(default_factory=list)
    guardrails: List[str] = field(default_factory=list)
    trailing_enabled: bool = False
    trailing_method: str | None = None
    trailing_atr_mult: float | None = None
    trail_stop_init: float | None = None
    trail_stop_last: float | None = None
    trail_updates: int = 0
    exit_reason: str | None = None

    def is_actionable(self) -> Tuple[bool, str]:
        if self.tradable is False:
            return False, "non_tradable"
        if not self.trace_id:
            return False, "missing_trace_id"
        if not self.desk_id:
            return False, "missing_desk_id"
        if not self.underlying:
            return False, "missing_underlying"
        if not self.instrument_type:
            return False, "missing_instrument_type"
        ok, reason = validate_trade_identity(
            self.underlying,
            self.instrument_type,
            self.expiry,
            self.strike,
            self.right,
        )
        if not ok:
            return False, reason
        if not self.instrument_id:
            return False, "missing_instrument_id"
        if self.side not in ("BUY", "SELL"):
            return False, "invalid_side"
        if self.entry_type not in ("LIMIT", "MARKET"):
            return False, "invalid_entry_type"
        if self.entry_price is None or self.entry_price <= 0:
            return False, "invalid_entry_price"
        if self.sl_price is None or self.sl_price <= 0:
            return False, "invalid_stop_loss"
        if self.tgt_price is None or self.tgt_price <= 0:
            return False, "invalid_target"
        if self.qty_lots is None or self.qty_lots <= 0:
            return False, "invalid_qty_lots"
        if self.qty_units is None or self.qty_units <= 0:
            return False, "invalid_qty_units"
        if self.validity_sec is None or self.validity_sec <= 0:
            return False, "invalid_validity"
        # sanity SL/TP checks
        if self.side == "BUY":
            if self.sl_price >= self.entry_price:
                return False, "stop_above_entry"
            if self.tgt_price <= self.entry_price:
                return False, "target_below_entry"
        if self.side == "SELL":
            if self.sl_price <= self.entry_price:
                return False, "stop_below_entry"
            if self.tgt_price >= self.entry_price:
                return False, "target_above_entry"
        # Basic expiry sanity: enforce only for options
        if self.instrument_type == "OPT":
            try:
                if self.expiry:
                    exp = datetime.fromisoformat(self.expiry).date()
                    if exp < now_ist().date():
                        return False, "expired_contract"
            except Exception:
                return False, "expiry_parse_failed"
        return True, "ok"

    def format_message(self) -> str:
        ist_ts = self.timestamp_ist or now_ist().isoformat()
        validity_min = int(max(1, round(self.validity_sec / 60)))
        guard = ", ".join(self.guardrails) if self.guardrails else "none"
        reasons = ", ".join(self.reason_codes) if self.reason_codes else "none"
        contract = self.instrument_id or "MISSING"
        trailing_line = ""
        if self.trailing_enabled:
            trailing_line = (
                f"\nInitial SL {self.sl_price} | Trailing SL {self.trail_stop_last or self.sl_price}"
                f" | Trail updates {int(self.trail_updates or 0)}"
            )
        return (
            f"TRADE TICKET | {ist_ts}\n"
            f"{self.underlying} {contract}\n"
            f"{self.side} {self.entry_type} @ {self.entry_price}\n"
            f"SL {self.sl_price} | TGT {self.tgt_price}\n"
            f"LOTS {self.qty_lots} | QTY {self.qty_units} | VALID {validity_min}m\n"
            f"{trailing_line}\n"
            f"REASON {reasons}\n"
            f"DO NOT TRADE IF: {guard}\n"
            f"NOTE: trailing stops are paper-simulated only (no broker-side SL modify)."
        )

    def format_market_note(self) -> str:
        ist_ts = self.timestamp_ist or now_ist().isoformat()
        contract = self.instrument_id or "MISSING_CONTRACT"
        reasons = self.tradable_reasons_blocking or ["blocked_by_unknown_reason"]
        reason_lines = "\n".join([f"- {reason}" for reason in reasons])
        return (
            f"MARKET NOTE | {ist_ts}\n"
            f"{self.underlying} {contract}\n"
            f"Not tradable due to:\n{reason_lines}"
        )

    @classmethod
    def from_trade(cls, trade, validity_sec: int, reason_codes: List[str], guardrails: List[str], desk_id: str):
        instrument_type = (getattr(trade, "instrument_type", None) or getattr(trade, "instrument", None))
        right = getattr(trade, "right", None) or getattr(trade, "option_type", None)
        expiry = getattr(trade, "expiry", None)
        strike = getattr(trade, "strike", None)
        instrument_id = build_instrument_id(
            getattr(trade, "symbol", None),
            instrument_type,
            expiry,
            strike,
            right,
        )
        return cls(
            trace_id=trade.trade_id,
            timestamp_epoch=getattr(trade, "timestamp_epoch", None) or datetime.now(timezone.utc).timestamp(),
            timestamp_ist=now_ist().isoformat(),
            desk_id=desk_id,
            underlying=getattr(trade, "symbol", None),
            instrument_type=instrument_type,
            expiry=expiry,
            strike=strike,
            right=right,
            instrument_id=instrument_id,
            side=getattr(trade, "side", None),
            entry_type=str(getattr(trade, "entry_type", None) or getattr(trade, "order_type", None) or "LIMIT").upper(),
            entry_price=float(getattr(trade, "entry_price", 0) or 0),
            sl_price=float(getattr(trade, "stop_loss", 0) or 0),
            tgt_price=float(getattr(trade, "target", 0) or 0),
            qty_lots=int(getattr(trade, "qty_lots", None) or getattr(trade, "qty", 0) or 0),
            qty_units=int(getattr(trade, "qty_units", None) or 0),
            validity_sec=int(validity_sec),
            tradable=bool(getattr(trade, "tradable", True)),
            tradable_reasons_blocking=list(getattr(trade, "tradable_reasons_blocking", []) or []),
            source_flags=dict(getattr(trade, "source_flags", {}) or {}),
            reason_codes=reason_codes,
            guardrails=guardrails,
            trailing_enabled=bool(getattr(trade, "trailing_enabled", False)),
            trailing_method=getattr(trade, "trailing_method", None),
            trailing_atr_mult=getattr(trade, "trailing_atr_mult", None),
            trail_stop_init=getattr(trade, "trail_stop_init", None),
            trail_stop_last=getattr(trade, "trail_stop_last", None),
            trail_updates=int(getattr(trade, "trail_updates", 0) or 0),
            exit_reason=getattr(trade, "exit_reason", None),
        )
