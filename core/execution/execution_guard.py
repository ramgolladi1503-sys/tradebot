from __future__ import annotations

from dataclasses import asdict, dataclass, field
from collections.abc import Mapping
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


def _safe_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _depth_levels(depth: Any, side: str) -> list[Any]:
    if not isinstance(depth, Mapping):
        return []
    levels = depth.get(side)
    if isinstance(levels, list):
        return levels
    return []


def _best_depth_price(depth: Any, side: str) -> float | None:
    levels = _depth_levels(depth, side)
    for level in levels:
        if isinstance(level, Mapping):
            price = _safe_float(level.get("price") or level.get("p"))
        else:
            price = None
        if price is not None and price > 0:
            return price
    return None


def _snapshot_reason_codes(snapshot: dict[str, Any] | None, *, evaluated_at_epoch: float | None, quote_age_limit: float) -> list[str]:
    if not isinstance(snapshot, Mapping):
        return []
    reasons: list[str] = []
    quote_source = _safe_text(snapshot.get("quote_source") or snapshot.get("option_ltp_source"))
    fallback_used = bool(snapshot.get("fallback_used"))
    if fallback_used or any(token in quote_source for token in ("fallback", "synthetic", "subscription_failed", "offhours")):
        reasons.append("fallback_quote")

    require_token = bool(snapshot.get("require_instrument_token"))
    actual_token = snapshot.get("instrument_token") or snapshot.get("option_token")
    expected_token = snapshot.get("expected_instrument_token") or snapshot.get("expected_option_token")
    if require_token and actual_token in (None, "", 0, "0"):
        reasons.append("missing_option_token")
    if expected_token not in (None, "", 0, "0") and str(actual_token) != str(expected_token):
        reasons.append("instrument_token_mismatch")

    has_depth_payload = isinstance(snapshot.get("depth"), Mapping) and bool(snapshot.get("depth"))
    depth_present = (
        bool(snapshot.get("require_depth"))
        or bool(snapshot.get("depth_required"))
        or has_depth_payload
        or snapshot.get("depth_age_sec") is not None
        or snapshot.get("last_depth_age_sec") is not None
        or snapshot.get("depth_ts") is not None
        or snapshot.get("depth_timestamp") is not None
    )
    depth = snapshot.get("depth")
    if depth_present:
        if not isinstance(depth, Mapping):
            reasons.append("missing_depth")
        else:
            best_buy = _best_depth_price(depth, "buy")
            best_sell = _best_depth_price(depth, "sell")
            if best_buy is None or best_sell is None:
                reasons.append("missing_depth")
            elif best_sell < best_buy:
                reasons.append("crossed_book")

        depth_age = _safe_float(snapshot.get("depth_age_sec"))
        if depth_age is None:
            depth_age = _safe_float(snapshot.get("last_depth_age_sec"))
        if depth_age is None and evaluated_at_epoch is not None:
            depth_ts = _safe_float(snapshot.get("depth_ts") or snapshot.get("depth_timestamp"))
            if depth_ts is not None:
                if depth_ts > 1e12:
                    depth_ts = depth_ts / 1000.0
                depth_age = float(evaluated_at_epoch) - depth_ts
        max_depth_age = _safe_float(snapshot.get("max_depth_age_sec"))
        if max_depth_age is None:
            max_depth_age = _safe_float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", None))
        if max_depth_age is None:
            max_depth_age = quote_age_limit
        if depth_age is not None and depth_age < 0:
            reasons.append("negative_depth_age")
        elif depth_age is not None and max_depth_age is not None and depth_age > max_depth_age:
            reasons.append("stale_depth")
    return reasons


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
    if bid_px is not None and ask_px is not None and ask_px < bid_px:
        reasons.append("crossed_book")
    if spread_pct is not None and spread_pct > spread_limit:
        reasons.append("spread_too_wide")
    reasons.extend(_snapshot_reason_codes(snapshot, evaluated_at_epoch=evaluated_at_epoch, quote_age_limit=age_limit))

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
