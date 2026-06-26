# core/strategy_requirements.py
import time
from typing import Dict, Any, List, Tuple

def validate_strategy_requirements(
    strategy_family: str,
    snapshot: Any,
    trade: Any,
    now_epoch: float,
    max_stale_sec: float = 120.0
) -> Tuple[bool, List[str]]:
    """
    Validates strict safety requirements based on strategy family.
    Returns (is_valid, list_of_veto_reasons).
    """
    vetoes = []
    
    # Common helper
    def _is_stale(last_ts: float) -> bool:
        if not last_ts or last_ts <= 0:
            return True
        return (now_epoch - last_ts) > max_stale_sec

    def _get(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    if strategy_family == "BREAKOUT_CONTINUATION":
        # Requires fresh underlying, fresh option quote, warmed OHLC, valid setup levels
        if _is_stale(_get(snapshot, "ts_epoch", 0)):
            vetoes.append("STALE_UNDERLYING")
        if _is_stale(_get(snapshot, "option_chain_last_ts", 0)):
            vetoes.append("STALE_OPTION_QUOTE")
            
        ohlc_bars = _get(snapshot, "ohlc_bars_count", 0)
        if ohlc_bars < 60:
            vetoes.append("WARMUP_INCOMPLETE")
            
        # Additional checks can be applied on `trade` for setup levels
        if not _get(trade, "entry_price", 0):
            vetoes.append("INVALID_SETUP_LEVELS")
            
    elif strategy_family in ("SELL_STRANGLE", "IRON_CONDOR"):
        # short_premium requires fresh underlying, fresh option chain, fresh bid/ask depth, 
        # IV/volatility inputs, range confirmation, and capped-risk structure.
        
        if _is_stale(_get(snapshot, "ts_epoch", 0)):
            vetoes.append("STALE_UNDERLYING")
        if _is_stale(_get(snapshot, "option_chain_last_ts", 0)):
            vetoes.append("STALE_OPTION_CHAIN")
            
        if not _get(snapshot, "depth_ok", True):
            vetoes.append("STALE_BID_ASK_DEPTH")
            
        raw = _get(snapshot, "raw_data", {})
        if not raw and isinstance(snapshot, dict):
            raw = snapshot
        if not raw or "atr" not in raw:
            vetoes.append("MISSING_VOLATILITY_INPUTS")
            
        if _get(snapshot, "regime", "") != "RANGE_BOUND":
            vetoes.append("NO_RANGE_CONFIRMATION")
            
        if strategy_family == "SELL_STRANGLE":
            vetoes.append("UNCAPPED_RISK_STRUCTURE")
            
    return (len(vetoes) == 0, vetoes)
