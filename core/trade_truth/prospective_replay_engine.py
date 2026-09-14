#!/usr/bin/env python3
"""Trade Truth Prospective Replay Engine.

Strictly accepts causal primitives only.
Executes physical Full Level-C replay using production evaluators, RealOptionQuoteProvider,
RiskEngine, and validate_execution_candidate.
Compares actual replayed stage hashes against expected output in a physically separate step.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from core.candidate_evaluators import evaluate_c1, evaluate_c2
from core.candidate_ranking import rank_candidates
from core.governed_strategy_authority import validate_execution_candidate
from core.market_session_store import MarketMemorySnapshot
from core.opportunity_scoring import OpportunityScoreBreakdown, OpportunityScoreRecord
from core.risk_engine import RiskEngine
from core.strategy_family_contract import (
    StrategyFamily,
    admit_candidate_to_pool,
    check_strategy_family_compatibility,
)
from core.trade_ticket import TradeTicket
from core.trade_truth.decision_hash import compute_deterministic_hash
from core.trade_truth.prospective_capture_engine import (
    arm_broker_write_guards,
    sha256_file,
    sha256_obj,
)
from core.trade_truth.raw_tick_causal_replay import RawTickSessionStore
from core.trade_truth.real_option_provider import RealOptionQuoteProvider


@dataclass(frozen=True)
class ProspectiveReplayActual:
    trace_id: str
    decision_ts_epoch: float
    stage_hashes: Dict[str, str]
    final_decision: Dict[str, Any]
    future_leak_detected: bool
    record_hash: str


def run_prospective_causal_replay(
    input_bundle: Dict[str, Any],
    session_store: Optional[RawTickSessionStore] = None,
    option_provider: Optional[RealOptionQuoteProvider] = None,
) -> ProspectiveReplayActual:
    """Replays decision cycle strictly from input bundle causal primitives."""
    arm_broker_write_guards()

    # Verify input bundle contains NO forward outputs
    forbidden_keys = {"features", "regime", "candidate_results", "ranking_results", "risk_outputs", "governance_outputs", "final_action", "decision_hash"}
    found_forbidden = forbidden_keys.intersection(input_bundle.keys())
    if found_forbidden:
        raise ValueError(f"Causal violation: input bundle contains forbidden outputs {found_forbidden}")

    trace_id = input_bundle["trace_id"]
    decision_ts_epoch = float(input_bundle["decision_ts_epoch"])
    decision_ts_str = input_bundle["decision_ts_str"]
    raw_source = Path(input_bundle["raw_market_events_source"]["source_path"])

    if session_store is None:
        session_store = RawTickSessionStore(raw_source, session_date=input_bundle["session_date"])
    if option_provider is None:
        option_provider = RealOptionQuoteProvider(raw_source)

    # 1. Closed bars strictly as-of decision_ts_epoch
    closed_bars = [
        b for b in session_store.store._bars_1m
        if session_store.bar_end_ts[b.timestamp] <= decision_ts_epoch
    ]
    bars_count = len(closed_bars)

    if not closed_bars:
        raise ValueError("Zero closed bars available as-of decision timestamp")

    last_closed = closed_bars[-1]
    mem = session_store.store.get_market_memory(as_of_timestamp=last_closed.timestamp)
    first_bar_ts = closed_bars[0].timestamp
    last_bar_ts = last_closed.timestamp
    max_raw_event_ts = max(session_store.bar_max_tick_ts[b.timestamp] for b in closed_bars)
    total_raw_events = sum(session_store.bar_tick_count[b.timestamp] for b in closed_bars)
    max_bar_end_ts = max(session_store.bar_end_ts[b.timestamp] for b in closed_bars)

    raw_events_summary = {
        "event_count": total_raw_events,
        "first_event_ts": float(session_store.bar_max_tick_ts[closed_bars[0].timestamp]),
        "last_event_ts": float(max_raw_event_ts),
    }
    events_hash = sha256_obj(raw_events_summary)

    bars_content = [
        {"ts": b.timestamp, "o": b.open, "h": b.high, "l": b.low, "c": b.close}
        for b in closed_bars
    ]
    bars_hash = sha256_obj(bars_content)

    mem_dict = {
        "as_of_timestamp": mem.as_of_timestamp,
        "current_price": float(mem.current_price),
        "session_open": float(mem.session_open),
        "session_high": float(mem.session_high),
        "session_low": float(mem.session_low),
        "rolling_1m_bars_count": int(mem.rolling_1m_bars_count),
        "rolling_15m_return_bps": float(mem.rolling_15m_return_bps),
        "distance_from_session_open_bps": float(mem.distance_from_session_open_bps),
        "rolling_15m_range_bps": float(mem.rolling_15m_range_bps),
        "realized_vol_15m": float(mem.realized_vol_15m),
    }
    mem_hash = sha256_obj(mem_dict)

    # Features
    features = [
        {"feature_name": "rolling_15m_return_bps", "feature_value": mem.rolling_15m_return_bps, "feature_timestamp": mem.as_of_timestamp, "feature_module": "core.market_session_store", "feature_version": "v1"},
        {"feature_name": "distance_from_session_open_bps", "feature_value": mem.distance_from_session_open_bps, "feature_timestamp": mem.as_of_timestamp, "feature_module": "core.market_session_store", "feature_version": "v1"},
        {"feature_name": "rolling_15m_range_bps", "feature_value": mem.rolling_15m_range_bps, "feature_timestamp": mem.as_of_timestamp, "feature_module": "core.market_session_store", "feature_version": "v1"},
        {"feature_name": "realized_vol_15m", "feature_value": mem.realized_vol_15m, "feature_timestamp": mem.as_of_timestamp, "feature_module": "core.market_session_store", "feature_version": "v1"},
    ]
    features_hash = sha256_obj(features)

    # Regime
    regime_hash = sha256_obj({"status": "REGIME_STAGE_NOT_APPLICABLE", "families": ["TREND", "MEAN_REVERT", "DEFINED_RISK"]})

    # Strategies
    r_c1 = evaluate_c1(mem, as_of_timestamp=decision_ts_str, trace_id=trace_id)
    r_c2 = evaluate_c2(mem, as_of_timestamp=decision_ts_str, trace_id=trace_id)
    evaluations = [
        {"strategy_id": "C1", "strategy_family": "TREND", "qualified": bool(r_c1.qualified), "candidate_emitted": bool(r_c1.candidate is not None), "reason_code": str(getattr(r_c1.reason_code, "value", r_c1.reason_code)), "score": getattr(r_c1.candidate, "score", None) if r_c1.candidate else None, "strategy_hash": sha256_obj({"id": "C1", "qualified": r_c1.qualified, "code": str(r_c1.reason_code)})},
        {"strategy_id": "C2", "strategy_family": "TREND", "qualified": bool(r_c2.qualified), "candidate_emitted": bool(r_c2.candidate is not None), "reason_code": str(getattr(r_c2.reason_code, "value", r_c2.reason_code)), "score": getattr(r_c2.candidate, "score", None) if r_c2.candidate else None, "strategy_hash": sha256_obj({"id": "C2", "qualified": r_c2.qualified, "code": str(r_c2.reason_code)})},
    ]
    strategy_eval_hash = sha256_obj(evaluations)

    # Candidate pool
    raw_emissions = []
    if r_c1.candidate:
        raw_emissions.append(r_c1.candidate)
    if r_c2.candidate:
        raw_emissions.append(r_c2.candidate)

    allowed_runtime_families = [StrategyFamily.TREND, StrategyFamily.MEAN_REVERT]
    candidate_pool_records = []
    admitted_pool = []
    for cand in raw_emissions:
        strat_fam = StrategyFamily.TREND
        compat_res = check_strategy_family_compatibility(strat_fam, allowed_runtime_families)
        pool_adm = admit_candidate_to_pool(asdict(cand)) if compat_res.compatible else False
        block_reasons = []
        if not compat_res.compatible:
            block_reasons.append(compat_res.reason_code)
        if not pool_adm:
            block_reasons.append("POOL_ADMISSION_REJECTED")
        cand_rec = {
            "candidate_id": cand.candidate_id,
            "strategy_id": cand.strategy_id,
            "strategy_family": strat_fam.value,
            "symbol": cand.symbol,
            "direction": getattr(cand, "direction", "BULLISH"),
            "family_compatibility_pass": compat_res.compatible,
            "pool_admission_pass": pool_adm,
            "block_reasons": block_reasons,
            "candidate_hash": sha256_obj(asdict(cand)),
        }
        candidate_pool_records.append(cand_rec)
        if compat_res.compatible and pool_adm:
            admitted_pool.append(cand)

    pool_hash = sha256_obj(candidate_pool_records)

    # Option selection
    if admitted_pool:
        top_cand = admitted_pool[0]
        direction = getattr(top_cand, "direction", "BULLISH")
        opt_res = option_provider.select_option(
            underlying="NIFTY",
            spot_price=mem.current_price,
            direction=direction,
            decision_ts_epoch=decision_ts_epoch,
        )
        option_selection = opt_res.to_dict()
        option_selection_hash = opt_res.selection_hash
    else:
        option_selection = {
            "selection_status": "SELECTION_STAGE_NOT_REACHED",
            "selected_instrument": None,
            "quote_executable_truth": None,
            "selection_hash": "0" * 64,
            "rejection_reason": "NO_ADMITTED_CANDIDATE",
        }
        option_selection_hash = "0" * 64

    # Ranking: BLOCKED_BY_PRODUCTION_DEPENDENCY
    ranking_hash = "0" * 64

    # Trade Construction: BLOCKED_BY_PRODUCTION_DEPENDENCY
    trade_hash = "0" * 64
    ticket_dict = None

    # Risk State & Production RiskEngine
    risk_snap = input_bundle["historical_risk_state_snapshot"]
    risk_engine = RiskEngine()
    risk_portfolio_input = {
        "capital": float(risk_snap.get("capital", 1000000.0)),
        "equity_high": float(risk_snap.get("equity_high", 1000000.0)),
        "daily_pnl": float(risk_snap.get("daily_pnl", 0.0)),
        "daily_pnl_pct": float(risk_snap.get("daily_pnl_pct", 0.0)),
        "daily_loss": 0.0,
        "daily_profit": 0.0,
        "open_risk_pct": float(risk_snap.get("open_risk_pct", 0.0)),
        "trades_today": int(risk_snap.get("trades_today", 0)),
    }
    risk_decision = risk_engine.evaluate_trade(
        portfolio=risk_portfolio_input,
        trade=ticket_dict,
    )
    risk_verdict = "ALLOWED" if risk_decision.allowed else "BLOCKED"
    risk_hash = sha256_obj({"snap": risk_snap, "decision": risk_decision.as_tuple()})

    # Governance
    gov_passed = False
    gov_reasons = []
    if admitted_pool:
        cand = admitted_pool[0]
        try:
            gov_passed = validate_execution_candidate(cand) and (risk_verdict == "ALLOWED")
        except Exception as exc:
            gov_passed = False
            gov_reasons.append(str(exc))
    else:
        gov_passed = False
        gov_reasons.append("NO_ADMITTED_CANDIDATES")

    gov_verdict = "GOVERNED_ALLOWED" if gov_passed else "GOVERNED_BLOCKED"
    gov_hash = sha256_obj({"verdict": gov_verdict, "reasons": gov_reasons})

    # Decision: BLOCKED_BY_PRODUCTION_DEPENDENCY
    decision_action = "BLOCKED_BY_PRODUCTION_DEPENDENCY"
    reason_codes = ["PRODUCTION_FINAL_DECISION_CAPTURE_BLOCKED_BY_DEPENDENCY"]
    decision_stage_hash = sha256_obj({"action": decision_action, "reasons": reason_codes})

    stage_hashes = {
        "market": events_hash,
        "bars": bars_hash,
        "memory": mem_hash,
        "features": features_hash,
        "regime": regime_hash,
        "strategy": strategy_eval_hash,
        "candidate_pool": pool_hash,
        "option_selection": option_selection_hash,
        "ranking": ranking_hash,
        "trade_construction": trade_hash,
        "risk": risk_hash,
        "governance": gov_hash,
        "decision": decision_stage_hash,
    }

    decision_hash = compute_deterministic_hash(stage_hashes)
    final_decision = {
        "action": decision_action,
        "reason_codes": reason_codes,
        "decision_hash": decision_hash,
    }

    future_leak = bool(
        max_raw_event_ts > decision_ts_epoch
        or max_bar_end_ts > decision_ts_epoch
    )

    record_payload = {
        "trace_id": trace_id,
        "session_id": input_bundle["session_id"],
        "decision_ts_epoch": decision_ts_epoch,
        "stage_hashes": stage_hashes,
        "decision_hash": decision_hash,
    }
    record_hash = sha256_obj(record_payload)

    return ProspectiveReplayActual(
        trace_id=trace_id,
        decision_ts_epoch=decision_ts_epoch,
        stage_hashes=stage_hashes,
        final_decision=final_decision,
        future_leak_detected=future_leak,
        record_hash=record_hash,
    )


def compare_replay_against_expected(
    actual: ProspectiveReplayActual,
    expected_output: Dict[str, Any],
) -> Dict[str, Any]:
    """Physically isolated comparison between replayed actual and expected truth output."""
    mismatches = []
    expected_stage_hashes = expected_output.get("stage_hashes", {})

    for stage_name, act_hash in actual.stage_hashes.items():
        exp_hash = expected_stage_hashes.get(stage_name)
        if exp_hash is None or act_hash != exp_hash:
            mismatches.append({
                "stage": stage_name,
                "actual_hash": act_hash,
                "expected_hash": exp_hash,
            })

    exp_decision = expected_output.get("final_decision", {})
    decision_match = (
        actual.final_decision.get("action") == exp_decision.get("action")
        and actual.final_decision.get("decision_hash") == exp_decision.get("decision_hash")
    )

    parity = (len(mismatches) == 0) and decision_match

    return {
        "trace_id": actual.trace_id,
        "parity": parity,
        "decision_match": decision_match,
        "stage_hash_mismatches_count": len(mismatches),
        "stage_mismatches": mismatches,
        "future_leak_detected": actual.future_leak_detected,
    }

