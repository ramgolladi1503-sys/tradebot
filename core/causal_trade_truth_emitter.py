"""Canonical Trade Truth Observation Adapter (Hops 11-12).

Wraps the established repository-native core.trade_truth models with NativePulse
context without inventing competing schemas or default positive truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.causal_pulse import NativePulse, sha256_canonical
from core.causal_shadow_decision import ShadowDecisionResult
from core.causal_strategy_harness import StrategyEvaluationResult
from core.trade_truth.models import (
    AnalyticalTruth,
    DecisionTruth,
    ExecutionTruth,
    IdentityTruth,
    MarketTruth,
    OutcomeTruth,
    ProvenanceTruth,
    TimingTruth,
    TradeTruthRecord,
)


def build_canonical_trade_truth(
    *,
    pulse: NativePulse,
    market_snapshot: Mapping[str, Any] | None,
    feed_health_truth: Mapping[str, Any] | None,
    strategy_result: StrategyEvaluationResult,
    decision_result: ShadowDecisionResult,
) -> TradeTruthRecord:
    """Assemble repository-native TradeTruthRecord preserving exact UNKNOWN semantics."""
    now_epoch = pulse.timestamp_epoch
    mkt = dict(market_snapshot or {})
    feed = dict(feed_health_truth or {})

    # Truth Law: UNKNOWN != TRUE, MISSING != ZERO
    underlying = str(mkt.get("underlying_symbol") or mkt.get("symbol") or "NIFTY")
    ltp = mkt.get("nifty_ltp") or mkt.get("ltp")

    market_truth = MarketTruth(
        underlying=underlying,
        ltp=float(ltp) if ltp is not None else None,
        bid=None,
        ask=None,
        spread=None,
        spread_pct=None,
    )

    primary_candidate = decision_result.selected_candidates[0] if decision_result.selected_candidates else None

    identity_truth = IdentityTruth(
        truth_record_id=f"truth_{pulse.session_id}_{pulse.sequence_num}",
        trace_id=pulse.pulse_id,
        session_id=pulse.session_id,
        candidate_id=primary_candidate.candidate_id if primary_candidate else "NONE",
        strategy_id=primary_candidate.strategy_id if primary_candidate else "NONE",
        instrument=primary_candidate.symbol if primary_candidate else underlying,
        parent_trace_id=pulse.parent_pulse_id,
        underlying=underlying,
    )

    timing_truth = TimingTruth(
        exchange_timestamp_epoch=pulse.timestamp_epoch,
        receive_timestamp_epoch=pulse.timestamp_epoch,
        normalization_timestamp_epoch=pulse.timestamp_epoch,
        decision_timestamp_epoch=pulse.timestamp_epoch,
        execution_boundary_timestamp_epoch=None,
    )

    analytical_truth = AnalyticalTruth(
        regime=strategy_result.regime,
        features_used={"evaluated_symbol_count": strategy_result.evaluated_symbol_count},
    )

    decision_truth = DecisionTruth(
        candidate_generated=bool(decision_result.selected_candidates),
        candidate_score=primary_candidate.confidence if primary_candidate else None,
        rank=1 if primary_candidate else None,
        ranking_reasons=tuple(r.get("reason_code", "UNKNOWN") for r in decision_result.rejected_decisions) or ("NO_CANDIDATE",),
        risk_result=decision_result.risk_verdict,
        governance_decision="ALLOWED" if decision_result.selected_candidates else "BLOCKED",
        final_action="OBSERVE",
        reason_codes=tuple(r.get("reason_code", "UNKNOWN") for r in decision_result.rejected_decisions) or ("NO_CANDIDATE",),
    )

    execution_truth = ExecutionTruth(
        intended_action="BUY" if (primary_candidate and primary_candidate.direction == "BUY") else "NO_TRADE",
        intended_entry=primary_candidate.entry_price if primary_candidate else None,
        executable_market_state="NOT_EXECUTABLE",
        theoretical_executable_price=primary_candidate.entry_price if primary_candidate else None,
        execution_type="OBSERVED_MARKET_EXECUTABILITY",
        broker_submission_authorized=False,
        actual_broker_submission=False,
        is_counterfactual=True,
    )

    outcome_truth = OutcomeTruth(
        is_counterfactual=True,
        status="PENDING",
    )

    provenance_truth = ProvenanceTruth(
        git_sha=pulse.producer_sha,
        dirty_tree=False,
        config_hash=pulse.payload_sha256,
    )

    body = {
        "identity": identity_truth.__dict__,
        "timing": timing_truth.__dict__,
        "market": market_truth.__dict__,
        "analytical": analytical_truth.__dict__,
        "decision": decision_truth.__dict__,
        "execution": execution_truth.__dict__,
        "outcome": outcome_truth.__dict__,
        "provenance": provenance_truth.__dict__,
    }
    payload_hash = sha256_canonical(body)

    return TradeTruthRecord(
        schema_version=1,
        source="tradebot.trade_truth.v1",
        identity=identity_truth,
        timing=timing_truth,
        market=market_truth,
        analytical=analytical_truth,
        decision=decision_truth,
        provenance=provenance_truth,
        execution=execution_truth,
        outcome=outcome_truth,
        live_decision_hash=payload_hash,
        record_hash=payload_hash,
        sequence_number=pulse.sequence_num,
        previous_record_hash=pulse.parent_pulse_id or "GENESIS",
        record_type="DECISION_TRUTH",
        parent_truth_record_id=pulse.parent_pulse_id,
        read_only=True,
        append_only=True,
        is_order_action=False,
        broker_api_called=False,
        orders_placed=0,
        orders_modified=0,
        orders_cancelled=0,
        integrity_status="VALID",
    )

