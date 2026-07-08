"""Adapter for bridging StrategyCandidates into replay-only execution signals."""

from __future__ import annotations
from typing import Any
import time

from config import config
from core.movement_contract import StrategyCandidate, StrategyContext, has_hard_blocker

UNSAFE_CANDIDATE_STATUSES = {"ADVISORY", "FALLBACK", "RECOVERED", "STALE", "DEBUG"}
UNSAFE_QUOTE_SOURCES = {"fallback", "synthetic", "proxy", "manual_stub"}

def adapt_candidate_to_signals(candidate: StrategyCandidate, ctx: StrategyContext, mode: str = "real") -> list[dict[str, Any]]:
    """Convert a StrategyCandidate into replay-only execution signals."""
    if not candidate.executable_eligible:
        return []
    
    status = str(candidate.status).strip().upper()
    if status in UNSAFE_CANDIDATE_STATUSES:
        return []
    
    if has_hard_blocker(candidate.blockers):
        return []
        
    evidence = candidate.evidence or {}
    metadata = getattr(candidate, 'metadata', getattr(ctx, 'metadata', {})) or {}
    params = getattr(candidate, "params", {}) or {}
    
    if str(evidence.get("recovered_fallback", "")).lower() == "true":
        return []
    if str(evidence.get("stale_quote", "")).lower() == "true":
        return []

    quote_source = str(evidence.get("quote_source", "")).lower()
    if quote_source in UNSAFE_QUOTE_SOURCES:
        return []

    spot = ctx.spot_ltp
    if spot is None or spot <= 0:
        return [{"lifecycle_state": "CANDIDATE_TO_SIGNAL_ADAPTER_REQUIRED", "blocked_reason": "MISSING_SPOT_LTP", "adapter_approved_for_replay": False}]

    if candidate.direction == "BUY_CALL":
        option_side = "CE"
    elif candidate.direction == "BUY_PUT":
        option_side = "PE"
    else:
        return []

    step = config.STRIKE_STEP_BY_SYMBOL.get(candidate.symbol)
    if step is None or step <= 0:
        if mode in ["fixture", "dev"]:
            step = 100
        else:
            return [{"lifecycle_state": "CANDIDATE_TO_SIGNAL_ADAPTER_REQUIRED", "blocked_reason": "MISSING_STRIKE_STEP_CONFIG", "adapter_approved_for_replay": False}]
            
    strike = round(spot / step) * step

    option_ltp = evidence.get("option_ltp")
    entry_price = None
    is_synthetic = False
    
    if option_ltp is not None and float(option_ltp) > 0 and quote_source and quote_source not in UNSAFE_QUOTE_SOURCES:
        entry_price = float(option_ltp)
    else:
        if mode in ["fixture", "dev"]:
            is_synthetic = True
            entry_price = spot * 0.004
            min_prem = getattr(config, "MIN_PREMIUM", 40)
            max_prem = getattr(config, "MAX_PREMIUM", 150)
            entry_price = max(entry_price, float(min_prem))
            entry_price = min(entry_price, float(max_prem))
        else:
            return [{"lifecycle_state": "CANDIDATE_TO_SIGNAL_ADAPTER_REQUIRED", "blocked_reason": "MISSING_VALID_OPTION_LTP", "adapter_approved_for_replay": False}]

    stop_loss = params.get("stop_loss") or evidence.get("stop_loss")
    target = params.get("target") or evidence.get("target")
    time_stop = params.get("time_stop") or params.get("max_holding_minutes") or evidence.get("time_stop") or evidence.get("max_holding_minutes")
    
    if stop_loss is None or target is None or time_stop is None:
        return [{"lifecycle_state": "CANDIDATE_TO_SIGNAL_ADAPTER_REQUIRED", "blocked_reason": "MISSING_RISK_REWARD_CONTRACT", "adapter_approved_for_replay": False}]

    confidence = 60
    if candidate.confidence_score is not None:
        confidence = int(candidate.confidence_score * 100)

    lineage_id = getattr(candidate, 'lineage', {}).get('lineage_id', metadata.get('lineage_id', 'L-' + str(int(time.time()))))
    expiry = metadata.get("expiry", "CURRENT_WEEK")
    source_rule_version = metadata.get("source_rule_version", "1.0")
    quote_age = evidence.get("quote_age", 0)

    sig = {
        "candidate_id": lineage_id,
        "strategy_id": candidate.strategy_id,
        "signal_ts": candidate.generated_epoch,
        "symbol": candidate.symbol,
        "direction": candidate.direction,
        "option_side": option_side,
        "selected_strike": strike,
        "expiry": expiry,
        "entry_price": round(entry_price, 2),
        "stop_loss": round(float(stop_loss), 2),
        "target": round(float(target), 2),
        "time_stop": int(time_stop),
        "confidence_score": confidence,
        "quote_source": quote_source if not is_synthetic else "synthetic_test_fixture",
        "quote_age": quote_age,
        "source_rule_version": source_rule_version,
        "safety_flags": ["STRICT_ADAPTER"],
        "strike_resolution_source": "STRIKE_STEP_BY_SYMBOL",
        "spot_ltp_used": spot,
        "strike_step_used": step,
        
        "live_allowed": False,
        "paper_live_allowed": False,
        "broker_order_allowed": False,
        "execution_allowed": False,
    }
    
    if is_synthetic:
        sig["certification_eligible"] = False
        sig["adapter_approved_for_replay"] = False
        sig["data_source"] = "synthetic_test_fixture"
    else:
        sig["certification_eligible"] = True
        sig["adapter_approved_for_replay"] = True
        
    return [sig]
