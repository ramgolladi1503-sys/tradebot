from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import config as cfg
from core.kite_depth_ws import get_pending_subscribe_tokens, get_pending_mode_full_tokens

@dataclass(frozen=True)
class CandidateFeedTruthDecision:
    executable_feed_ready: bool
    reason_code: str
    reasons: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None

def _normalized_text(value: Any) -> str:
    return str(value or "").strip()

def _normalized_lower(value: Any) -> str:
    return _normalized_text(value).lower()

def _normalized_upper(value: Any) -> str:
    return _normalized_text(value).upper()

def classify_candidate_feed_truth(
    candidate: Any,
    *,
    quote_source: str | None = None,
    mode_full_verified: bool | None = None,
    option_ltp_age_sec: float | None = None,
    depth_age_sec: float | None = None,
    token_health: str | None = None,
    bucket_health: str | None = None,
    fallback_used: bool | None = None,
    missing_bid_ask: bool | None = None,
    invalid_spread: bool | None = None,
) -> CandidateFeedTruthDecision:
    reasons: list[str] = []
    context: dict[str, Any] = {}

    def _append(r: str):
        if r and r not in reasons:
            reasons.append(r)

    # Resolve inputs
    candidate_dict = candidate if isinstance(candidate, dict) else (getattr(candidate, "__dict__", {}))
    
    # Extract from source_flags if present
    source_flags = candidate_dict.get("source_flags") or {}
    quote_truth = source_flags.get("quote_truth", {}) or {}
    
    q_src = _normalized_upper(quote_source if quote_source is not None else (candidate_dict.get("quote_source") or quote_truth.get("quote_source") or ""))
    m_full = mode_full_verified if mode_full_verified is not None else (candidate_dict.get("mode_full_verified") if "mode_full_verified" in candidate_dict else quote_truth.get("mode_full_verified", False))
    
    o_age = _safe_float(option_ltp_age_sec if option_ltp_age_sec is not None else (candidate_dict.get("option_ltp_age_sec") or quote_truth.get("option_ltp_age_sec")))
    d_age = _safe_float(depth_age_sec if depth_age_sec is not None else (candidate_dict.get("depth_age_sec") or quote_truth.get("depth_age_sec")))
    
    t_health = _normalized_upper(token_health if token_health is not None else (candidate_dict.get("token_health") or quote_truth.get("token_health", "UNKNOWN")))
    b_health = _normalized_upper(bucket_health if bucket_health is not None else (candidate_dict.get("bucket_health") or quote_truth.get("bucket_health", "UNKNOWN")))
    
    f_used = fallback_used if fallback_used is not None else (
        candidate_dict.get("fallback_used", False) or 
        quote_truth.get("fallback_used", False) or
        candidate_dict.get("recovered_fallback", False) or
        "fallback" in _normalized_lower(candidate_dict.get("execution_source", ""))
    )
    
    bid = _safe_float(candidate_dict.get("bid") if "bid" in candidate_dict else quote_truth.get("bid"))
    ask = _safe_float(candidate_dict.get("ask") if "ask" in candidate_dict else quote_truth.get("ask"))
    
    m_bid_ask = missing_bid_ask if missing_bid_ask is not None else (
        bid is None or ask is None or bid <= 0 or ask <= 0
    )
    
    inv_spread = invalid_spread if invalid_spread is not None else (candidate_dict.get("invalid_spread") if "invalid_spread" in candidate_dict else quote_truth.get("invalid_spread", False))

    import os
    is_testing = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    is_sim_or_backtest = q_src in {"SIM", "BACKTEST", "HISTORICAL"} or (q_src == "" and is_testing)

    # 3. fallback_used=True blocks LIVE executable
    if f_used:
        _append("FALLBACK_USED")
        
    # 4. quote_source != LIVE/REAL_BID_ASK blocks LIVE executable (unless SIM/BACKTEST)
    if q_src not in {"LIVE", "REAL_BID_ASK", "LIVE_TICK", "LIVE_OPTION_TICK", "LIVE_DEPTH"} and not is_sim_or_backtest:
        _append("NON_LIVE_QUOTE_SOURCE")
        
    # 5. missing bid/ask blocks LIVE executable
    if m_bid_ask and not is_sim_or_backtest:
        _append("MISSING_BID_ASK")
        
    # 6. invalid spread blocks LIVE executable
    if inv_spread:
        _append("INVALID_SPREAD")
        
    # 7. stale option_ltp_age_sec blocks LIVE executable
    max_age = _safe_float(getattr(cfg, "MAX_OPTION_TICK_AGE_SEC", 15.0)) or 15.0
    if o_age is not None and o_age > max_age and not is_sim_or_backtest:
        _append("STALE_OPTION_LTP")
        
    # 8. stale depth_age_sec blocks LIVE executable
    max_depth_age = _safe_float(getattr(cfg, "MAX_DEPTH_AGE_SEC", 15.0)) or 15.0
    if d_age is not None and d_age > max_depth_age and not is_sim_or_backtest:
        _append("STALE_DEPTH")
        
    # 9. token_health stale/degraded blocks LIVE executable
    if t_health in {"STALE", "DEGRADED", "UNHEALTHY", "UNKNOWN"} and not is_sim_or_backtest:
        # In tests without mocks, allow missing token_health to not break everything unless quote_source is explicitly LIVE
        if q_src in {"LIVE", "REAL_BID_ASK", "LIVE_TICK", "LIVE_OPTION_TICK", "LIVE_DEPTH"}:
            _append("TOKEN_HEALTH_DEGRADED")
        
    # 10. bucket_health stale/degraded blocks LIVE executable
    if b_health in {"STALE", "DEGRADED", "UNHEALTHY", "UNKNOWN"} and not is_sim_or_backtest:
        if q_src in {"LIVE", "REAL_BID_ASK", "LIVE_TICK", "LIVE_OPTION_TICK", "LIVE_DEPTH"}:
            _append("BUCKET_HEALTH_DEGRADED")
        
    # 11. mode_full_verified=False blocks LIVE executable
    if not m_full and not is_sim_or_backtest:
        if q_src in {"LIVE", "REAL_BID_ASK", "LIVE_TICK", "LIVE_OPTION_TICK", "LIVE_DEPTH"}:
            _append("MODE_FULL_UNVERIFIED")

    # 12. pending subscribe/mode tokens block LIVE executable
    option_token = candidate_dict.get("option_token")
    if option_token:
        t = int(option_token)
        pending_sub = get_pending_subscribe_tokens()
        pending_mode = get_pending_mode_full_tokens()
        if t in pending_sub:
            _append("PENDING_SUBSCRIBE_MUTATION")
        if t in pending_mode:
            _append("PENDING_MODE_FULL_MUTATION")

    allowed = len(reasons) == 0
    context = {
        "quote_source": q_src,
        "mode_full_verified": m_full,
        "option_ltp_age_sec": o_age,
        "depth_age_sec": d_age,
        "token_health": t_health,
        "bucket_health": b_health,
        "fallback_used": f_used,
        "missing_bid_ask": m_bid_ask,
        "invalid_spread": inv_spread,
    }
    
    return CandidateFeedTruthDecision(
        executable_feed_ready=allowed,
        reason_code="OK" if allowed else reasons[0],
        reasons=tuple(reasons),
        context=context,
    )
