"""Canonical 8-Dimensional Trade Truth Emitter (Hops 11-12).

Emits structured, append-only TradeTruth records containing Identity, Timing,
Market, Analytical, Decision, Risk, Execution, and Outcome truth dimensions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from core.causal_pulse import NativePulse, sha256_canonical
from core.causal_shadow_decision import ShadowDecisionResult
from core.causal_strategy_harness import StrategyEvaluationResult


@dataclass(frozen=True)
class CanonicalTradeTruthRecord:
    pulse_id: str
    session_id: str
    sequence_num: int
    producer_sha: str
    timestamp_epoch: float
    timestamp_ist: str
    
    # 8 Truth Dimensions
    identity_truth: dict[str, Any]
    timing_truth: dict[str, Any]
    market_truth: dict[str, Any]
    analytical_truth: dict[str, Any]
    decision_truth: dict[str, Any]
    risk_truth: dict[str, Any]
    execution_truth: dict[str, Any]
    outcome_truth: dict[str, Any]
    
    payload_sha256: str = ""
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pulse_id": self.pulse_id,
            "session_id": self.session_id,
            "sequence_num": self.sequence_num,
            "producer_sha": self.producer_sha,
            "timestamp_epoch": self.timestamp_epoch,
            "timestamp_ist": self.timestamp_ist,
            "identity_truth": self.identity_truth,
            "timing_truth": self.timing_truth,
            "market_truth": self.market_truth,
            "analytical_truth": self.analytical_truth,
            "decision_truth": self.decision_truth,
            "risk_truth": self.risk_truth,
            "execution_truth": self.execution_truth,
            "outcome_truth": self.outcome_truth,
            "payload_sha256": self.payload_sha256,
        }


def build_canonical_trade_truth(
    *,
    pulse: NativePulse,
    market_snapshot: Mapping[str, Any] | None,
    feed_health_truth: Mapping[str, Any] | None,
    strategy_result: StrategyEvaluationResult,
    decision_result: ShadowDecisionResult,
) -> CanonicalTradeTruthRecord:
    """Assemble verified 8D TradeTruthRecord."""
    now_epoch = pulse.timestamp_epoch

    identity_truth = {
        "pulse_id": pulse.pulse_id,
        "session_id": pulse.session_id,
        "sequence_num": pulse.sequence_num,
        "producer_sha": pulse.producer_sha,
        "schema_version": 1,
    }

    timing_truth = {
        "pulse_timestamp_epoch": pulse.timestamp_epoch,
        "pulse_timestamp_ist": pulse.timestamp_ist,
        "evaluation_epoch": now_epoch,
    }

    market_truth = {
        "market_open": (market_snapshot or {}).get("market_open", True),
        "underlying_symbol": "NIFTY 50",
        "underlying_ltp": (market_snapshot or {}).get("nifty_ltp"),
        "feed_state": (feed_health_truth or {}).get("feed_truth_state", "UNKNOWN"),
        "websocket_ok": (feed_health_truth or {}).get("websocket_ok", True),
    }

    analytical_truth = {
        "regime": strategy_result.regime,
        "evaluated_symbol_count": strategy_result.evaluated_symbol_count,
        "rejections_count": len(strategy_result.rejections),
    }

    decision_truth = {
        "candidates_count": len(strategy_result.candidates),
        "selected_count": len(decision_result.selected_candidates),
        "rejected_decisions_count": len(decision_result.rejected_decisions),
        "rejection_sample": strategy_result.rejections[:3],
    }

    risk_truth = {
        "risk_verdict": decision_result.risk_verdict,
        "max_portfolio_exposure": decision_result.max_portfolio_exposure,
        "broker_write_authority": False,
        "order_authority": False,
        "orders_placed": 0,
    }

    execution_truth = {
        "mode": "SIM_SHADOW_OBSERVATION",
        "orders_routed": 0,
        "read_only": True,
        "broker_api_called": False,
    }

    outcome_truth = {
        "prospective_tracking_enabled": True,
        "forward_horizons_sec": [300, 900, 1800],
        "outcome_state": "PENDING_FORWARD_EVALUATION",
    }

    body = {
        "identity_truth": identity_truth,
        "timing_truth": timing_truth,
        "market_truth": market_truth,
        "analytical_truth": analytical_truth,
        "decision_truth": decision_truth,
        "risk_truth": risk_truth,
        "execution_truth": execution_truth,
        "outcome_truth": outcome_truth,
    }
    payload_hash = sha256_canonical(body)

    return CanonicalTradeTruthRecord(
        pulse_id=pulse.pulse_id,
        session_id=pulse.session_id,
        sequence_num=pulse.sequence_num,
        producer_sha=pulse.producer_sha,
        timestamp_epoch=pulse.timestamp_epoch,
        timestamp_ist=pulse.timestamp_ist,
        identity_truth=identity_truth,
        timing_truth=timing_truth,
        market_truth=market_truth,
        analytical_truth=analytical_truth,
        decision_truth=decision_truth,
        risk_truth=risk_truth,
        execution_truth=execution_truth,
        outcome_truth=outcome_truth,
        payload_sha256=payload_hash,
    )
