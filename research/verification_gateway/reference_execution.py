"""Small, independent event-tape reference for synthetic execution tests only.

No strategy/runtime code is imported. Prices and fees are Decimal-based to
make assumptions explicit and prevent binary-float drift in the fixture.
This is not a broker model or historical fill simulator.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Sequence


@dataclass(frozen=True)
class SyntheticQuote:
    event_time: datetime
    available_time: datetime
    instrument_id: str
    contract_id: str
    bid: Decimal
    ask: Decimal


@dataclass(frozen=True)
class SyntheticDecision:
    decided_at: datetime
    instrument_id: str
    contract_id: str
    side: str


@dataclass(frozen=True)
class SyntheticFill:
    event_time: datetime
    available_time: datetime
    contract_id: str
    side: str
    price: Decimal
    fee: Decimal


@dataclass(frozen=True)
class SyntheticRoundTrip:
    entry: SyntheticFill
    exit: SyntheticFill
    gross_pnl: Decimal
    total_fees: Decimal
    net_pnl: Decimal


def _aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label}_MUST_BE_TIMEZONE_AWARE")


def _price(value: Decimal | str | int, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"INVALID_{label}") from None
    if not result.is_finite() or result <= 0:
        raise ValueError(f"INVALID_{label}")
    return result


def _first_eligible_quote(
    quotes: Sequence[SyntheticQuote], decision: SyntheticDecision
) -> SyntheticQuote:
    _aware(decision.decided_at, "DECISION_TIME")
    candidates = []
    for quote in quotes:
        _aware(quote.event_time, "QUOTE_EVENT_TIME")
        _aware(quote.available_time, "QUOTE_AVAILABLE_TIME")
        bid, ask = _price(quote.bid, "BID"), _price(quote.ask, "ASK")
        if ask < bid:
            raise ValueError("CROSSED_QUOTE")
        if quote.available_time < quote.event_time:
            raise ValueError("QUOTE_AVAILABLE_BEFORE_EVENT")
        if quote.instrument_id != decision.instrument_id or quote.contract_id != decision.contract_id:
            continue
        # A quote must be generated and published no earlier than the decision.
        if quote.event_time >= decision.decided_at and quote.available_time >= decision.decided_at:
            candidates.append(quote)
    if not candidates:
        raise ValueError("NO_POST_DECISION_QUOTE")
    return min(candidates, key=lambda item: (item.available_time, item.event_time))


def _fill(
    quote: SyntheticQuote,
    decision: SyntheticDecision,
    *,
    side: str,
    fee_bps: Decimal,
    slippage_bps: Decimal,
) -> SyntheticFill:
    if side not in {"BUY", "SELL"}:
        raise ValueError("UNSUPPORTED_SIDE")
    if quote.available_time < decision.decided_at or quote.event_time < decision.decided_at:
        raise ValueError("FILL_BEFORE_DECISION_OR_KNOWLEDGE")
    base = quote.ask if side == "BUY" else quote.bid
    bps = Decimal("10000")
    adjusted = base * (Decimal(1) + slippage_bps / bps) if side == "BUY" else base * (Decimal(1) - slippage_bps / bps)
    if adjusted <= 0:
        raise ValueError("NONPOSITIVE_FILL")
    fee = adjusted * fee_bps / bps
    return SyntheticFill(quote.event_time, quote.available_time, quote.contract_id, side, adjusted, fee)


def replay_long_round_trip(
    quotes: Sequence[SyntheticQuote],
    *,
    entry_decision: SyntheticDecision,
    exit_decision: SyntheticDecision,
    fee_bps: Decimal | str | int,
    slippage_bps: Decimal | str | int,
) -> SyntheticRoundTrip:
    """Buy then sell one synthetic contract at the next eligible quotes."""
    _aware(entry_decision.decided_at, "ENTRY_DECISION_TIME")
    _aware(exit_decision.decided_at, "EXIT_DECISION_TIME")
    if entry_decision.side != "BUY":
        raise ValueError("BUY_ONLY_ENTRY_REQUIRED")
    if exit_decision.side != "SELL":
        raise ValueError("SELL_EXIT_REQUIRED")
    if (entry_decision.instrument_id, entry_decision.contract_id) != (
        exit_decision.instrument_id, exit_decision.contract_id
    ):
        raise ValueError("ENTRY_EXIT_CONTRACT_MISMATCH")
    if exit_decision.decided_at <= entry_decision.decided_at:
        raise ValueError("EXIT_DECISION_NOT_AFTER_ENTRY")
    fee = _price(Decimal(1) + Decimal(str(fee_bps)) / Decimal(10000), "FEE_RATE") - Decimal(1)
    slip = _price(Decimal(1) + Decimal(str(slippage_bps)) / Decimal(10000), "SLIPPAGE_RATE") - Decimal(1)
    if fee < 0 or slip < 0:
        raise ValueError("NEGATIVE_COST_RATE")
    entry_quote = _first_eligible_quote(quotes, entry_decision)
    entry = _fill(entry_quote, entry_decision, side="BUY", fee_bps=fee * 10000, slippage_bps=slip * 10000)
    exit_quote = _first_eligible_quote(quotes, exit_decision)
    if exit_quote.available_time <= entry.available_time:
        raise ValueError("EXIT_FILL_NOT_AFTER_ENTRY_FILL")
    exit_fill = _fill(exit_quote, exit_decision, side="SELL", fee_bps=fee * 10000, slippage_bps=slip * 10000)
    if exit_fill.contract_id != entry.contract_id:
        raise ValueError("FILL_CONTRACT_MISMATCH")
    gross = exit_fill.price - entry.price
    total_fees = entry.fee + exit_fill.fee
    return SyntheticRoundTrip(entry, exit_fill, gross, total_fees, gross - total_fees)
