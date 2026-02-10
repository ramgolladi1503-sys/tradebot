"""DecisionBuilder converts pipeline dicts into Decision objects.

This module avoids heavy imports and can be used by any pipeline stage
that already has plain Python dicts for market/strategy/signals.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.decision import (
    Decision,
    DecisionMarket,
    DecisionMeta,
    DecisionOutcome,
    DecisionRisk,
    DecisionSignals,
    DecisionStatus,
    DecisionStrategy,
)


_REQUIRED_FIELDS_BY_FAMILY = {
    "vol": {"iv"},
    "options_iv": {"iv", "ivp"},
    "skew": {"iv", "ivp"},
}


def _missing_required_fields(strategy_family: Optional[str], market: Dict[str, Any]) -> List[str]:
    if not strategy_family:
        return []
    required = _REQUIRED_FIELDS_BY_FAMILY.get(strategy_family, set())
    missing = []
    for field in required:
        if market.get(field) is None:
            missing.append(f"missing_{field}")
    return missing


def build_decision(
    meta: Dict[str, Any],
    market: Dict[str, Any],
    signals: Optional[Dict[str, Any]] = None,
    strategy: Optional[Dict[str, Any]] = None,
    risk: Optional[Dict[str, Any]] = None,
    outcome: Optional[Dict[str, Any]] = None,
    strategy_family: Optional[str] = None,
) -> Decision:
    """Build a Decision from plain dicts.

    Missing optional fields are set to None. If a field is required for a
    strategy family, a reject reason is appended (e.g., missing_iv).
    """
    signals = signals or {}
    strategy = strategy or {}
    risk = risk or {}
    outcome = outcome or {}

    reject_reasons = list(outcome.get("reject_reasons", []))
    reject_reasons.extend(_missing_required_fields(strategy_family, market))

    meta_obj = DecisionMeta(
        ts_epoch=float(meta.get("ts_epoch", 0.0)),
        run_id=str(meta.get("run_id", "")),
        symbol=str(meta.get("symbol", "")),
        timeframe=str(meta.get("timeframe", "")),
    )
    market_obj = DecisionMarket(
        spot=float(market.get("spot", 0.0)),
        vwap=market.get("vwap"),
        trend_state=str(market.get("trend_state", "")),
        regime=str(market.get("regime", "")),
        vol_state=str(market.get("vol_state", "")),
        iv=market.get("iv"),
        ivp=market.get("ivp"),
    )
    signals_obj = DecisionSignals(
        pattern_flags=list(signals.get("pattern_flags", [])),
        rank_score=signals.get("rank_score"),
        confidence=signals.get("confidence"),
    )
    strategy_obj = DecisionStrategy(
        name=str(strategy.get("name", "")),
        legs=list(strategy.get("legs", [])),
        direction=str(strategy.get("direction", "")),
        entry_reason=str(strategy.get("entry_reason", "")),
        stop=float(strategy.get("stop", 0.0) or 0.0),
        target=float(strategy.get("target", 0.0) or 0.0),
        rr=float(strategy.get("rr", 0.0) or 0.0),
        max_loss=float(strategy.get("max_loss", 0.0) or 0.0),
        size=float(strategy.get("size", 0.0) or 0.0),
    )
    risk_obj = DecisionRisk(
        daily_loss_limit=float(risk.get("daily_loss_limit", 0.0) or 0.0),
        position_limit=float(risk.get("position_limit", 0.0) or 0.0),
        slippage_bps_assumed=float(risk.get("slippage_bps_assumed", 0.0) or 0.0),
    )
    status = outcome.get("status", DecisionStatus.PLANNED.value)
    outcome_obj = DecisionOutcome(
        status=DecisionStatus(status),
        reject_reasons=reject_reasons,
    )

    return Decision(
        meta=meta_obj,
        market=market_obj,
        signals=signals_obj,
        strategy=strategy_obj,
        risk=risk_obj,
        outcome=outcome_obj,
        extra={
            k: v for k, v in outcome.items() if k not in {"status", "reject_reasons"}
        },
    )


# Example: Trade decision with legs
# decision = build_decision(
#     meta={"ts_epoch": 1720000000.0, "run_id": "R1", "symbol": "NIFTY", "timeframe": "1m"},
#     market={"spot": 25200.0, "trend_state": "UP", "regime": "TREND", "vol_state": "LOW"},
#     signals={"pattern_flags": ["breakout"], "rank_score": 0.72, "confidence": 0.6},
#     strategy={
#         "name": "trend_breakout",
#         "legs": [{"type": "OPT", "strike": 25200, "right": "CE", "qty": 50}],
#         "direction": "BUY",
#         "entry_reason": "breakout",
#         "stop": 25100.0,
#         "target": 25450.0,
#         "rr": 2.5,
#         "max_loss": 5000.0,
#         "size": 1,
#     },
#     risk={"daily_loss_limit": 0.02, "position_limit": 3, "slippage_bps_assumed": 8},
# )
#
# Example: No-trade decision with reject reasons
# decision = build_decision(
#     meta={"ts_epoch": 1720000000.0, "run_id": "R2", "symbol": "NIFTY", "timeframe": "1m"},
#     market={"spot": 25200.0, "trend_state": "FLAT", "regime": "RANGE", "vol_state": "LOW"},
#     outcome={"status": "skipped", "reject_reasons": ["spread_too_wide", "feed_stale"]},
# )
