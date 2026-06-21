import os
import copy
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Structure: _PERSISTENCE_STATE_CACHE[surface_name][cache_key] = event_dict
_PERSISTENCE_STATE_CACHE: Dict[str, Dict[str, Dict[str, Any]]] = {}

_PERSISTENCE_COMPRESSION_SEEN: Dict[str, int] = {}
_PERSISTENCE_COMPRESSION_SUPPRESSED: Dict[str, int] = {}

def reset_persistence_compression_cache():
    global _PERSISTENCE_STATE_CACHE, _PERSISTENCE_COMPRESSION_SEEN, _PERSISTENCE_COMPRESSION_SUPPRESSED
    _PERSISTENCE_STATE_CACHE.clear()
    _PERSISTENCE_COMPRESSION_SEEN.clear()
    _PERSISTENCE_COMPRESSION_SUPPRESSED.clear()

def _extract_cache_key(event: Dict[str, Any]) -> str:
    instr_type = str(event.get("instrument_type", "UNKNOWN"))
    sym = str(event.get("symbol", "UNKNOWN"))
    strat = str(event.get("strategy_id", "UNKNOWN"))
    side = str(event.get("side", "UNKNOWN"))
    strike = str(event.get("strike", "0"))
    expiry = str(event.get("expiry", "UNKNOWN"))
    opt_type = str(event.get("option_type", "UNKNOWN"))
    return f"{instr_type}_{sym}_{strat}_{side}_{strike}_{expiry}_{opt_type}"

def _is_meaningful_transition(cached: Dict[str, Any], incoming: Dict[str, Any]) -> bool:
    try:
        score_cached = float(cached.get("score_0_100", 0.0) or 0.0)
        score_inc = float(incoming.get("score_0_100", 0.0) or 0.0)
        if abs(score_inc - score_cached) >= 2.0:
            return True
            
        proba_cached = float(cached.get("xgb_proba", 0.0) or 0.0)
        proba_inc = float(incoming.get("xgb_proba", 0.0) or 0.0)
        if abs(proba_inc - proba_cached) >= 0.02:
            return True
            
        spread_cached = float(cached.get("spread_pct", 0.0) or 0.0)
        spread_inc = float(incoming.get("spread_pct", 0.0) or 0.0)
        if abs(spread_inc - spread_cached) >= 0.005:
            return True

        # Check execution states and reasons
        fields_to_check = [
            "regime",
            "gatekeeper_allowed",
            "pilot_allowed",
            "risk_allowed",
            "executable",
            "execution_allowed",
            "veto_reasons",
            "pilot_reasons",
            "hard_reject_reason",
            "first_blocking_gate",
            "quote_freshness_status",
            "latency_status"
        ]
        
        for field in fields_to_check:
            if str(cached.get(field, "")) != str(incoming.get(field, "")):
                return True
                
        return False
    except Exception:
        # If parsing fails, default to writing to be safe
        return True

def should_write_persistent_state(event: Dict[str, Any], surface_name: str) -> bool:
    disable_compression = bool(int(os.getenv("DISABLE_PERSISTENCE_COMPRESSION", "0")))
    if disable_compression:
        return True

    if surface_name not in _PERSISTENCE_COMPRESSION_SEEN:
        _PERSISTENCE_COMPRESSION_SEEN[surface_name] = 0
        _PERSISTENCE_COMPRESSION_SUPPRESSED[surface_name] = 0
        _PERSISTENCE_STATE_CACHE[surface_name] = {}

    _PERSISTENCE_COMPRESSION_SEEN[surface_name] += 1

    cache_key = _extract_cache_key(event)
    cached_state = _PERSISTENCE_STATE_CACHE[surface_name].get(cache_key)
    
    if cached_state is not None:
        if not _is_meaningful_transition(cached_state, event):
            _PERSISTENCE_COMPRESSION_SUPPRESSED[surface_name] += 1
            suppressed = _PERSISTENCE_COMPRESSION_SUPPRESSED[surface_name]
            if suppressed % 100 == 0:
                seen = _PERSISTENCE_COMPRESSION_SEEN[surface_name]
                ratio = suppressed / max(1, seen)
                logger.info(f"persistence_compression threshold_met surface={surface_name} suppressed_writes={suppressed} ratio={ratio:.2f}")
            return False
            
    return True

def record_written_state(event: Dict[str, Any], surface_name: str):
    disable_compression = bool(int(os.getenv("DISABLE_PERSISTENCE_COMPRESSION", "0")))
    if disable_compression:
        return

    if surface_name not in _PERSISTENCE_STATE_CACHE:
        _PERSISTENCE_STATE_CACHE[surface_name] = {}

    cache_key = _extract_cache_key(event)
    _PERSISTENCE_STATE_CACHE[surface_name][cache_key] = copy.copy(event)
