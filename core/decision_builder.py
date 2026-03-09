"""DecisionBuilder converts pipeline dicts into Decision objects.

This module avoids heavy imports and can be used by any pipeline stage
that already has plain Python dicts for market/strategy/signals.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from config import config as cfg
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
from core.decision_snapshot import DecisionSnapshot


_REQUIRED_FIELDS_BY_FAMILY = {
    "vol": {"iv"},
    "options_iv": {"iv", "ivp"},
    "skew": {"iv", "ivp"},
}


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        out = float(value)
    except Exception:
        return None
    if out != out:  # NaN guard
        return None
    return out


def _signal_result_payload(signal_result: Any) -> Dict[str, Any]:
    if signal_result is None:
        return {}
    if hasattr(signal_result, "to_dict"):
        try:
            payload = signal_result.to_dict()
            if isinstance(payload, Mapping):
                return dict(payload)
        except Exception:
            pass
    if isinstance(signal_result, Mapping):
        return dict(signal_result)
    return {
        "confidence": getattr(signal_result, "confidence", None),
        "features": getattr(signal_result, "features", None),
        "direction": getattr(signal_result, "direction", None),
    }


def _execution_decision_payload(execution_decision: Any) -> Dict[str, Any]:
    if execution_decision is None:
        return {}
    if hasattr(execution_decision, "to_dict"):
        try:
            payload = execution_decision.to_dict()
            if isinstance(payload, Mapping):
                return dict(payload)
        except Exception:
            pass
    if isinstance(execution_decision, Mapping):
        return dict(execution_decision)
    return {
        "can_execute": getattr(execution_decision, "can_execute", None),
        "execution_score": getattr(execution_decision, "execution_score", None),
        "execution_reject_reason": getattr(execution_decision, "execution_reject_reason", None),
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
    decision_snapshot: Optional[DecisionSnapshot | Dict[str, Any]] = None,
    signal_result: Optional[Any] = None,
    execution_decision: Optional[Any] = None,
) -> Decision:
    """Build a Decision from plain dicts.

    Missing optional fields are set to None. If a field is required for a
    strategy family, a reject reason is appended (e.g., missing_iv).
    """
    signals = signals or {}
    strategy = strategy or {}
    risk = risk or {}
    outcome = outcome or {}
    market = dict(market or {})

    reject_reasons = list(outcome.get("reject_reasons", []))
    reject_reasons.extend(_missing_required_fields(strategy_family, market))

    snapshot_obj: DecisionSnapshot | None = None
    if bool(getattr(cfg, "USE_DECISION_SNAPSHOT", False)) and decision_snapshot is not None:
        if isinstance(decision_snapshot, DecisionSnapshot):
            snapshot_obj = decision_snapshot
        elif isinstance(decision_snapshot, dict):
            snapshot_obj = DecisionSnapshot.from_dict(decision_snapshot)
        if snapshot_obj is not None:
            # Snapshot becomes source-of-truth for spot-like value when feature is enabled.
            if snapshot_obj.index_price is not None:
                market["spot"] = float(snapshot_obj.index_price)

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
    signal_payload = _signal_result_payload(signal_result)
    signal_features = signal_payload.get("features")
    if not isinstance(signal_features, Mapping):
        signal_features = {}
    signal_conf = _safe_float(signal_payload.get("confidence"))
    if signal_conf is None:
        signal_conf = _safe_float(signals.get("confidence"))
    rank_score = signal_features.get("rank_score")
    if rank_score is None:
        rank_score = signals.get("rank_score")
    pattern_flags = signal_features.get("pattern_flags")
    if not isinstance(pattern_flags, list):
        pattern_flags = list(signals.get("pattern_flags", []))

    signals_obj = DecisionSignals(
        pattern_flags=list(pattern_flags),
        rank_score=rank_score,
        confidence=signal_conf,
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

    extra_payload = {
        k: v for k, v in outcome.items() if k not in {"status", "reject_reasons"}
    }
    if snapshot_obj is not None:
        extra_payload["decision_snapshot"] = snapshot_obj.to_dict()
    if signal_payload:
        extra_payload["signal_v1"] = {
            "confidence": signal_conf,
            "features": dict(signal_features),
            "direction": str(signal_payload.get("direction") or strategy.get("direction") or ""),
        }
    exec_payload = _execution_decision_payload(execution_decision)
    if exec_payload:
        extra_payload["execution_v1"] = {
            "can_execute": bool(exec_payload.get("can_execute")),
            "execution_score": _safe_float(exec_payload.get("execution_score")) or 0.0,
            "execution_reject_reason": (
                str(exec_payload.get("execution_reject_reason"))
                if exec_payload.get("execution_reject_reason") is not None
                else None
            ),
        }

    return Decision(
        meta=meta_obj,
        market=market_obj,
        signals=signals_obj,
        strategy=strategy_obj,
        risk=risk_obj,
        outcome=outcome_obj,
        extra=extra_payload,
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
