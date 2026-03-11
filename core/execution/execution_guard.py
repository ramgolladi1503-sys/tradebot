from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from config import config as cfg

from .entry_pricer import ExecutionEntryDecision, resolve_execution_entry


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


@dataclass(frozen=True)
class ExecutionGuardDecision:
    execution_allowed: bool
    execution_entry: float | None
    execution_entry_source: str
    reasons: list[str] = field(default_factory=list)
    quote_age_sec: float | None = None
    max_quote_age_sec: float | None = None
    spread_pct: float | None = None
    max_spread_pct: float | None = None
    reference_price: float | None = None
    price_mismatch_pct: float | None = None
    price_mismatch_abs: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_execution_guard(
    *,
    side: str,
    bid: Any,
    ask: Any,
    snapshot: dict[str, Any] | None = None,
    evaluated_at_epoch: float | None = None,
    max_quote_age_sec: float | None = None,
    max_spread_pct: float | None = None,
    reference_price: Any = None,
) -> ExecutionGuardDecision:
    age_limit = float(
        max_quote_age_sec
        if max_quote_age_sec is not None
        else getattr(cfg, "LIVE_MAX_QUOTE_AGE_SEC", getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0))
    )
    spread_limit = float(
        max_spread_pct
        if max_spread_pct is not None
        else getattr(cfg, "EXEC_MAX_SPREAD_PCT", getattr(cfg, "MAX_SPREAD_PCT", 0.015))
    )
    entry_decision: ExecutionEntryDecision = resolve_execution_entry(
        side=side,
        bid=bid,
        ask=ask,
        snapshot=snapshot,
        evaluated_at_epoch=evaluated_at_epoch,
        max_quote_age_sec=age_limit,
    )
    reasons: list[str] = []
    bid_px = entry_decision.bid
    ask_px = entry_decision.ask
    spread_pct = None
    if bid_px is not None and ask_px is not None and max(ask_px, bid_px) > 0:
        mid = (bid_px + ask_px) / 2.0
        if mid > 0:
            spread_pct = max(0.0, ask_px - bid_px) / mid
    if not entry_decision.executable:
        reasons.append(entry_decision.reason)
    if spread_pct is not None and spread_pct > spread_limit:
        reasons.append("spread_too_wide")

    reference_px = _safe_float(reference_price)
    mismatch_pct = None
    mismatch_abs = None
    if entry_decision.execution_entry is not None and reference_px is not None and reference_px > 0:
        mismatch_abs = abs(entry_decision.execution_entry - reference_px)
        mismatch_pct = mismatch_abs / abs(reference_px)
        if mismatch_pct > float(getattr(cfg, "ENTRY_MISMATCH_PCT", 0.25)):
            reasons.append("price_mismatch")

    deduped_reasons = list(dict.fromkeys([str(r) for r in reasons if str(r).strip()]))
    return ExecutionGuardDecision(
        execution_allowed=len(deduped_reasons) == 0,
        execution_entry=entry_decision.execution_entry,
        execution_entry_source=entry_decision.source,
        reasons=deduped_reasons,
        quote_age_sec=entry_decision.quote_age_sec,
        max_quote_age_sec=age_limit,
        spread_pct=spread_pct,
        max_spread_pct=spread_limit,
        reference_price=reference_px,
        price_mismatch_pct=mismatch_pct,
        price_mismatch_abs=mismatch_abs,
    )
