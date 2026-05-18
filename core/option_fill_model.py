"""Realistic option paper fill and slippage model.

This module calculates paper fill prices from quote snapshots. It does not
create orders, mutate paper order state, mutate ledgers, write files, call
brokers, or wire runtime execution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

OPTION_FILL_MODEL_SCHEMA_VERSION = 1
BUY_ENTRY = "BUY_ENTRY"
BUY_EXIT = "BUY_EXIT"
FILL_APPROVED = "FILL_APPROVED"
FILL_REJECTED = "FILL_REJECTED"


class OptionFillModelError(ValueError):
    """Raised when fill model input is invalid."""


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if out == out else None


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _to_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    return None


def _list_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


def _spread_pct(bid: float, ask: float) -> float:
    mid = (bid + ask) / 2.0
    if mid <= 0.0:
        return 0.0
    return ((ask - bid) / mid) * 100.0


@dataclass(frozen=True)
class OptionFillDecision:
    schema_version: int
    state: str
    fill_type: str
    approved: bool
    quantity: int
    bid: float | None
    ask: float | None
    ltp: float | None
    depth: float | None
    quote_age_sec: float | None
    spread_pct: float | None
    slippage_pct: float
    reference_price: float | None
    fill_price: float | None
    estimated_notional: float
    estimated_slippage_cost: float
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    broker_order_action: bool = False
    live_order_action: bool = False
    is_order_action: bool = False
    append: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["reasons"] = list(self.reasons)
        return payload


def build_option_fill_decision(
    quote_snapshot: Any,
    *,
    fill_type: str,
    quantity: int,
    max_quote_age_sec: float = 2.5,
    max_spread_pct: float = 3.0,
    min_depth: float = 1.0,
    slippage_pct: float = 0.25,
) -> OptionFillDecision:
    """Calculate a conservative paper fill decision from bid/ask quote data.

    BUY entry uses ask plus slippage. BUY exit uses bid minus slippage. LTP-only
    quotes are rejected because they create fake fills.
    """

    quote = _to_mapping(quote_snapshot)
    normalized_type = str(fill_type or "").strip().upper()
    blockers: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []

    if normalized_type not in {BUY_ENTRY, BUY_EXIT}:
        raise OptionFillModelError(f"unsupported_fill_type:{normalized_type}")

    qty = _as_int(quantity, default=0)
    if qty <= 0:
        blockers.append("QUANTITY_MISSING")

    if quote is None:
        blockers.append("QUOTE_SNAPSHOT_MISSING")
        quote = {}
    else:
        blockers.extend(_list_of_strings(quote.get("blockers")))
        warnings.extend(_list_of_strings(quote.get("warnings")))

    bid = _as_float(quote.get("bid"))
    ask = _as_float(quote.get("ask"))
    ltp = _as_float(quote.get("ltp") if quote.get("ltp") is not None else quote.get("last_price"))
    depth = _as_float(quote.get("depth"))
    quote_age_sec = _as_float(quote.get("quote_age_sec") if quote.get("quote_age_sec") is not None else quote.get("age_sec"))
    fallback_used = _bool(quote.get("fallback_used"), default=False)
    advisory_only = _bool(quote.get("advisory_only"), default=False)

    if bid is None or bid <= 0.0:
        blockers.append("QUOTE_BID_MISSING")
    if ask is None or ask <= 0.0:
        blockers.append("QUOTE_ASK_MISSING")
    if ltp is None or ltp <= 0.0:
        blockers.append("QUOTE_LTP_MISSING")
    if bid is not None and ask is not None and bid > 0.0 and ask > 0.0 and ask < bid:
        blockers.append("QUOTE_ASK_BELOW_BID")
    if bid is None or ask is None:
        blockers.append("LTP_ONLY_FILL_REJECTED")
    if fallback_used:
        blockers.append("FALLBACK_QUOTE_REJECTED")
    if advisory_only:
        blockers.append("ADVISORY_QUOTE_REJECTED")
    if quote_age_sec is None:
        blockers.append("QUOTE_AGE_MISSING")
    elif quote_age_sec > float(max_quote_age_sec):
        blockers.append("QUOTE_STALE")
    if depth is None:
        blockers.append("QUOTE_DEPTH_MISSING")
    elif depth < float(min_depth):
        blockers.append("QUOTE_DEPTH_BELOW_MIN")

    spread = None
    if bid is not None and ask is not None and bid > 0.0 and ask > 0.0 and ask >= bid:
        spread = round(_spread_pct(bid, ask), 6)
        if spread > float(max_spread_pct):
            blockers.append("QUOTE_SPREAD_TOO_WIDE")

    slippage = max(0.0, float(slippage_pct))
    reference_price = None
    fill_price = None
    estimated_notional = 0.0
    slippage_cost = 0.0

    if not blockers:
        if normalized_type == BUY_ENTRY:
            reference_price = ask
            fill_price = ask * (1.0 + slippage / 100.0)
            slippage_cost = (fill_price - ask) * qty
        else:
            reference_price = bid
            fill_price = bid * (1.0 - slippage / 100.0)
            slippage_cost = (bid - fill_price) * qty
        fill_price = round(max(0.0, float(fill_price)), 6)
        reference_price = round(float(reference_price), 6)
        estimated_notional = round(float(fill_price) * qty, 6)
        slippage_cost = round(float(slippage_cost), 6)
        reasons.append("paper_fill_price_calculated_from_bid_ask_with_slippage")

    normalized_blockers = _dedupe(blockers)
    approved = not normalized_blockers
    if not approved:
        reasons.append("paper_fill_rejected_by_quote_quality_gate")

    return OptionFillDecision(
        schema_version=OPTION_FILL_MODEL_SCHEMA_VERSION,
        state=FILL_APPROVED if approved else FILL_REJECTED,
        fill_type=normalized_type,
        approved=approved,
        quantity=qty,
        bid=round(float(bid), 6) if bid is not None else None,
        ask=round(float(ask), 6) if ask is not None else None,
        ltp=round(float(ltp), 6) if ltp is not None else None,
        depth=round(float(depth), 6) if depth is not None else None,
        quote_age_sec=round(float(quote_age_sec), 6) if quote_age_sec is not None else None,
        spread_pct=spread,
        slippage_pct=round(float(slippage), 6),
        reference_price=reference_price,
        fill_price=fill_price,
        estimated_notional=estimated_notional,
        estimated_slippage_cost=slippage_cost,
        blockers=normalized_blockers,
        warnings=_dedupe(warnings),
        reasons=tuple(sorted({reason for reason in reasons if reason})),
    )


__all__ = [
    "BUY_ENTRY",
    "BUY_EXIT",
    "FILL_APPROVED",
    "FILL_REJECTED",
    "OPTION_FILL_MODEL_SCHEMA_VERSION",
    "OptionFillDecision",
    "OptionFillModelError",
    "build_option_fill_decision",
]
