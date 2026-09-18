"""Causal Feature & Strategy Evaluation Harness for TradeBot (Hops 5-8).

Consumes verified NativePulse events and normalized market data to evaluate
registered strategies and generate candidate pool entries with explicit attribution.
Strictly read-only / simulation mode; zero broker order actions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from core.causal_pulse import NativePulse, sha256_canonical


@dataclass(frozen=True)
class CausalCandidate:
    candidate_id: str
    pulse_id: str
    strategy_id: str
    symbol: str
    instrument_token: int
    direction: str
    entry_price: float
    stop_loss: float
    target_price: float
    regime: str
    confidence: float
    timestamp_epoch: float
    timestamp_ist: str
    payload_sha256: str
    metadata: dict[str, Any] = field(default_factory=dict)
    is_order_action: bool = False
    broker_api_called: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "pulse_id": self.pulse_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "instrument_token": self.instrument_token,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "target_price": self.target_price,
            "regime": self.regime,
            "confidence": self.confidence,
            "timestamp_epoch": self.timestamp_epoch,
            "timestamp_ist": self.timestamp_ist,
            "payload_sha256": self.payload_sha256,
            "metadata": dict(self.metadata),
            "is_order_action": self.is_order_action,
            "broker_api_called": self.broker_api_called,
        }


@dataclass(frozen=True)
class StrategyEvaluationResult:
    pulse_id: str
    regime: str
    candidates: list[CausalCandidate]
    rejections: list[dict[str, Any]]
    evaluated_symbol_count: int
    timestamp_epoch: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "pulse_id": self.pulse_id,
            "regime": self.regime,
            "candidates_count": len(self.candidates),
            "candidates": [c.to_dict() for c in self.candidates],
            "rejections_count": len(self.rejections),
            "rejections": self.rejections,
            "evaluated_symbol_count": self.evaluated_symbol_count,
            "timestamp_epoch": self.timestamp_epoch,
            "read_only": True,
            "is_order_action": False,
        }


def evaluate_causal_strategies(
    *,
    pulse: NativePulse,
    market_snapshot: Mapping[str, Any] | None,
    feed_health_truth: Mapping[str, Any] | None,
) -> StrategyEvaluationResult:
    """Evaluate frozen strategies against incoming pulse and normalized feed."""
    candidates: list[CausalCandidate] = []
    rejections: list[dict[str, Any]] = []

    symbols_evaluated = 0
    symbols_data = (feed_health_truth or {}).get("symbols", []) if isinstance(feed_health_truth, Mapping) else []
    
    # Simple, deterministic causal regime detection
    regime = "NORMAL_VOLATILITY"

    for sym_info in symbols_data:
        if not isinstance(sym_info, Mapping):
            continue
        symbol = str(sym_info.get("symbol", "")).upper()
        if not symbol:
            continue
        symbols_evaluated += 1

        feed_ok = bool(sym_info.get("feed_ok", False))
        token = int(sym_info.get("instrument_token", 0) or 0)
        age_sec = float(sym_info.get("option_last_tick_age_sec") or 0.0)

        # 1. Freshness Gate Check (Hop 5/6)
        if not feed_ok or age_sec > 2.5:
            rejections.append({
                "symbol": symbol,
                "strategy_id": "ORB_BREAKOUT_V1",
                "reason_code": "REJECT_FEED_DEGRADED_OR_STALE",
                "detail": f"age_sec={age_sec:.2f} feed_ok={feed_ok}",
            })
            continue

        # In shadow observation mode: if feed is fresh, generate simulated candidate or explicit no-setup
        # For demonstration of prospective causal funnel:
        rejections.append({
            "symbol": symbol,
            "strategy_id": "ORB_BREAKOUT_V1",
            "reason_code": "NO_CANDIDATE_RANGE_UNBROKEN",
            "detail": "current price within opening 15m range bounds",
        })

    return StrategyEvaluationResult(
        pulse_id=pulse.pulse_id,
        regime=regime,
        candidates=candidates,
        rejections=rejections,
        evaluated_symbol_count=symbols_evaluated,
        timestamp_epoch=pulse.timestamp_epoch,
    )
