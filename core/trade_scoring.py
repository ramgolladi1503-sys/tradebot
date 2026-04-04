from __future__ import annotations
from core.paths import logs_dir

from pathlib import Path
import json
from config import config as cfg


def _safe_float(value):
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _clamp01(value: float | None, *, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    return max(0.0, min(1.0, float(value)))


def _weighted_average(parts: list[tuple[float | None, float]]) -> float:
    total_weight = 0.0
    total_score = 0.0
    for value, weight in parts:
        if value is None or weight <= 0:
            continue
        total_score += float(value) * float(weight)
        total_weight += float(weight)
    if total_weight <= 0:
        return 0.0
    return _clamp01(total_score / total_weight, default=0.0)


def _candidate_value(candidate, field: str, default=None):
    if isinstance(candidate, dict):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def apply_adaptive_thresholds(
    candidate,
    base_score: float,
    *,
    market_mode: str | None = None,
) -> dict[str, float | str | bool | int | None]:
    normalized_mode = str(
        market_mode
        or _candidate_value(candidate, "market_mode")
        or ((_candidate_value(candidate, "source_flags", {}) or {}).get("market_mode"))
        or getattr(cfg, "EXECUTION_MODE", "LIVE")
    ).strip().upper()
    neutral = {
        "adjusted_score": round(float(base_score), 6),
        "adaptive_threshold_adjustment": 0.0,
        "adaptive_threshold_impact_score": 0.0,
        "adaptive_threshold_applied": False,
        "adaptive_threshold_key": None,
        "adaptive_threshold_count": 0,
    }
    if normalized_mode not in {"SIM", "PAPER", "OFFHOURS"}:
        return neutral
    if not bool(getattr(cfg, "OFFLINE_THRESHOLD_LEARNING_ENABLE", False)):
        return neutral
    try:
        from core.adaptive_thresholds import score_adjustment_from_impact
        from core.threshold_audit import load_threshold_impact
    except Exception:
        return neutral
    strategy_family = str(_candidate_value(candidate, "strategy_family") or "unknown").strip().lower() or "unknown"
    stage = str(_candidate_value(candidate, "rejected_at_stage") or "selector").strip().lower() or "selector"
    impact_rows = load_threshold_impact()
    row = impact_rows.get(f"{stage}:{strategy_family}") or impact_rows.get(f"selector:{strategy_family}")
    if not isinstance(row, dict):
        return neutral
    sample_count = int(row.get("count") or 0)
    min_samples = max(1, int(getattr(cfg, "OFFLINE_THRESHOLD_LEARNING_MIN_SAMPLES", 20) or 20))
    if sample_count < min_samples:
        return {
            **neutral,
            "adaptive_threshold_key": f"{stage}:{strategy_family}",
            "adaptive_threshold_count": sample_count,
        }
    impact_score = float(_safe_float(row.get("impact_score")) or 0.0)
    impact_confidence = _clamp01(_safe_float(row.get("impact_confidence")), default=0.0)
    adjustment = score_adjustment_from_impact(float(impact_score) * float(impact_confidence))
    adjusted_score = _clamp01(float(base_score) + float(adjustment), default=0.0)
    return {
        "adjusted_score": round(float(adjusted_score), 6),
        "adaptive_threshold_adjustment": round(float(adjustment), 6),
        "adaptive_threshold_impact_score": round(float(impact_score), 6),
        "adaptive_threshold_applied": bool(abs(float(adjustment)) > 0.0),
        "adaptive_threshold_key": f"{stage}:{strategy_family}",
        "adaptive_threshold_count": sample_count,
    }


def _adaptive_priority_weights(
    candidate,
    *,
    stale_quote: bool,
    spread_uncertain: bool,
    data_confidence: float | None,
) -> tuple[float, float, list[str]]:
    signal_weight = float(getattr(cfg, "PRIORITY_SCORE_WEIGHT_SIGNAL", 0.62))
    execution_weight = float(getattr(cfg, "PRIORITY_SCORE_WEIGHT_EXECUTION", 0.38))
    source_flags = _candidate_value(candidate, "source_flags", {}) or {}
    regime = str(
        _candidate_value(candidate, "regime")
        or source_flags.get("regime")
        or source_flags.get("regime_day")
        or "NEUTRAL"
    ).strip().upper()
    trend_mode = str(
        _candidate_value(candidate, "trend_mode")
        or source_flags.get("trend_mode")
        or ("SIDEWAYS" if regime in {"RANGE", "RANGE_VOLATILE", "NEUTRAL"} else "")
    ).strip().upper()
    range_mode_raw = _candidate_value(candidate, "range_mode")
    if range_mode_raw is None:
        range_mode_raw = source_flags.get("range_mode")
    range_mode = bool(range_mode_raw)
    volatility_mode = str(
        _candidate_value(candidate, "volatility_mode")
        or source_flags.get("volatility_mode")
        or ("HIGH" if regime in {"EVENT", "PANIC"} else "NORMAL")
    ).strip().upper()
    reasons: list[str] = []
    if regime == "TREND" and not range_mode and trend_mode != "SIDEWAYS":
        bonus = float(getattr(cfg, "PRIORITY_SCORE_TREND_SIGNAL_BONUS", 0.08))
        signal_weight += bonus
        execution_weight = max(0.05, execution_weight - (bonus * 0.5))
        reasons.append("trend_signal_bonus")
    if regime in {"RANGE", "RANGE_VOLATILE", "NEUTRAL"} or range_mode or trend_mode == "SIDEWAYS":
        bonus = float(getattr(cfg, "PRIORITY_SCORE_SIDEWAYS_EXECUTION_BONUS", 0.10))
        execution_weight += bonus
        signal_weight = max(0.05, signal_weight - (bonus * 0.5))
        reasons.append("sideways_execution_bonus")
    if volatility_mode == "HIGH" or stale_quote or spread_uncertain:
        bonus = float(getattr(cfg, "PRIORITY_SCORE_UNSTABLE_EXECUTION_BONUS", 0.14))
        execution_weight += bonus
        signal_weight = max(0.05, signal_weight - (bonus * 0.25))
        reasons.append("unstable_execution_bonus")
    soft_floor = float(getattr(cfg, "DATA_CONFIDENCE_EXECUTION_SOFT_FLOOR", 0.45) or 0.45)
    if data_confidence is not None and float(data_confidence) < soft_floor:
        bonus = float(getattr(cfg, "PRIORITY_SCORE_LOW_DATA_CONFIDENCE_EXECUTION_BONUS", 0.08))
        execution_weight += bonus
        signal_weight = max(0.05, signal_weight - (bonus * 0.25))
        reasons.append("low_data_confidence_execution_bonus")
    total = max(signal_weight + execution_weight, 1e-6)
    return (
        round(float(signal_weight / total), 6),
        round(float(execution_weight / total), 6),
        reasons,
    )


def compute_final_score(
    candidate,
    *,
    candidate_class: str,
    market_mode: str,
    setup_quality: float | None,
    confluence_score: float | None,
    regime_fit: float | None,
    liquidity_quality: float | None,
    freshness_quality: float | None,
    execution_feasibility: float | None,
    data_confidence: float | None = None,
    setup_score: float | None = None,
    trigger_score: float | None = None,
    entry_quality_score: float | None = None,
    family_survival_score: float | None = None,
    risk_learning_adjustment: float | None = None,
    risk_learning_confidence: float | None = None,
    is_fallback: bool = False,
    stale_quote: bool = False,
    missing_liquidity: bool = False,
    spread_uncertain: bool = False,
) -> dict:
    """
    Strong final ranking contract that separates setup quality from execution readiness.
    This is additive and does not replace existing raw trade scoring outputs.
    """
    normalized_class = str(candidate_class or "ADVISORY_ONLY").strip().upper() or "ADVISORY_ONLY"
    normalized_mode = str(market_mode or "").strip().upper()
    family_feedback = {
        "family_score_adjustment": 0.0,
        "family_signal_bias_adjustment": 0.0,
        "family_execution_bias_adjustment": 0.0,
        "family_confidence": 0.0,
        "family_feedback_applied": False,
        "expectancy_score": 0.0,
        "generated_at": None,
        "version": None,
    }
    strategy_weight = {
        "strategy_weight_adjustment": 0.0,
        "strategy_weight_confidence": 0.0,
        "strategy_execution_bias_adjustment": 0.0,
        "strategy_signal_bias_adjustment": 0.0,
        "strategy_weight_applied": False,
        "generated_at": None,
        "version": None,
    }
    if bool(getattr(cfg, "OFFLINE_FAMILY_LEARNING_ENABLE", False)) and normalized_mode in {"SIM", "PAPER", "OFFHOURS"}:
        try:
            from core.offline_family_learning import lookup_family_feedback

            family_feedback = lookup_family_feedback(
                _candidate_value(candidate, "strategy_family"),
                _candidate_value(candidate, "direction_family"),
            )
        except Exception:
            family_feedback = dict(family_feedback)
    if bool(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_LEARNING_ENABLE", False)) and normalized_mode in {"SIM", "PAPER", "OFFHOURS"}:
        try:
            from core.strategy_weight_learning import lookup_strategy_weight

            strategy_weight = lookup_strategy_weight(
                _candidate_value(candidate, "strategy_family"),
                _candidate_value(candidate, "direction_family"),
            )
        except Exception:
            strategy_weight = dict(strategy_weight)
    setup_component = _clamp01(
        setup_score if setup_score is not None else _safe_float(_candidate_value(candidate, "setup_score")),
        default=_clamp01(setup_quality, default=0.0),
    )
    trigger_component = _clamp01(
        trigger_score if trigger_score is not None else _safe_float(_candidate_value(candidate, "trigger_score")),
        default=_clamp01(confluence_score, default=0.0),
    )
    entry_quality_component = _clamp01(
        entry_quality_score if entry_quality_score is not None else _safe_float(_candidate_value(candidate, "entry_quality_score")),
        default=_clamp01(execution_feasibility, default=0.0),
    )
    family_survival_component = _clamp01(
        family_survival_score if family_survival_score is not None else _safe_float(_candidate_value(candidate, "family_survival_score")),
        default=0.5,
    )
    signal_score = _weighted_average(
        [
            (_clamp01(setup_quality, default=0.0), float(getattr(cfg, "FINAL_SCORE_WEIGHT_SETUP_QUALITY", 0.30))),
            (_clamp01(confluence_score, default=0.0), float(getattr(cfg, "FINAL_SCORE_WEIGHT_CONFLUENCE", 0.16))),
            (_clamp01(regime_fit, default=0.0), float(getattr(cfg, "FINAL_SCORE_WEIGHT_REGIME_FIT", 0.14))),
            (setup_component, float(getattr(cfg, "FINAL_SCORE_WEIGHT_SETUP_QUALITY", 0.30))),
            (trigger_component, float(getattr(cfg, "FINAL_SCORE_WEIGHT_TRIGGER_QUALITY", 0.12))),
        ]
    )
    execution_score = _weighted_average(
        [
            (_clamp01(liquidity_quality, default=0.0), float(getattr(cfg, "FINAL_SCORE_WEIGHT_LIQUIDITY", 0.14))),
            (_clamp01(freshness_quality, default=0.0), float(getattr(cfg, "FINAL_SCORE_WEIGHT_FRESHNESS", 0.10))),
            (
                _clamp01(execution_feasibility, default=0.0),
                float(getattr(cfg, "FINAL_SCORE_WEIGHT_EXECUTION_FEASIBILITY", 0.16)),
            ),
            (
                _clamp01(data_confidence, default=0.0),
                float(getattr(cfg, "FINAL_SCORE_WEIGHT_DATA_CONFIDENCE", 0.12)),
            ),
            (
                entry_quality_component,
                float(getattr(cfg, "FINAL_SCORE_WEIGHT_ENTRY_QUALITY", 0.14)),
            ),
        ]
    )
    priority_weight_signal, priority_weight_execution, adaptive_weight_reasons = _adaptive_priority_weights(
        candidate,
        stale_quote=stale_quote,
        spread_uncertain=spread_uncertain,
        data_confidence=data_confidence,
    )
    max_family_adjustment = max(
        0.0,
        float(getattr(cfg, "OFFLINE_FAMILY_LEARNING_MAX_ADJUSTMENT", 0.06) or 0.06),
    )
    max_family_bias = max_family_adjustment * 0.5
    max_strategy_adjustment = max(
        0.0,
        float(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MAX_ADJUSTMENT", 0.04) or 0.04),
    )
    max_strategy_signal_bias = max(
        0.0,
        float(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MAX_SIGNAL_BIAS", 0.015) or 0.015),
    )
    max_strategy_execution_bias = max(
        0.0,
        float(getattr(cfg, "OFFLINE_STRATEGY_WEIGHT_MAX_EXECUTION_BIAS", 0.015) or 0.015),
    )
    family_signal_bias_adjustment = max(
        -max_family_bias,
        min(max_family_bias, _safe_float(family_feedback.get("family_signal_bias_adjustment")) or 0.0),
    )
    family_execution_bias_adjustment = max(
        -max_family_bias,
        min(max_family_bias, _safe_float(family_feedback.get("family_execution_bias_adjustment")) or 0.0),
    )
    if family_signal_bias_adjustment or family_execution_bias_adjustment:
        priority_weight_signal = max(0.05, float(priority_weight_signal) + float(family_signal_bias_adjustment))
        priority_weight_execution = max(0.05, float(priority_weight_execution) + float(family_execution_bias_adjustment))
        total_weight = max(priority_weight_signal + priority_weight_execution, 1e-6)
        priority_weight_signal = float(priority_weight_signal) / total_weight
        priority_weight_execution = float(priority_weight_execution) / total_weight
        adaptive_weight_reasons = list(adaptive_weight_reasons or [])
        adaptive_weight_reasons.append("family_feedback_bias")
    strategy_signal_bias_adjustment = max(
        -max_strategy_signal_bias,
        min(max_strategy_signal_bias, _safe_float(strategy_weight.get("strategy_signal_bias_adjustment")) or 0.0),
    )
    strategy_execution_bias_adjustment = max(
        -max_strategy_execution_bias,
        min(max_strategy_execution_bias, _safe_float(strategy_weight.get("strategy_execution_bias_adjustment")) or 0.0),
    )
    if strategy_signal_bias_adjustment or strategy_execution_bias_adjustment:
        priority_weight_signal = max(0.05, float(priority_weight_signal) + float(strategy_signal_bias_adjustment))
        priority_weight_execution = max(0.05, float(priority_weight_execution) + float(strategy_execution_bias_adjustment))
        total_weight = max(priority_weight_signal + priority_weight_execution, 1e-6)
        priority_weight_signal = float(priority_weight_signal) / total_weight
        priority_weight_execution = float(priority_weight_execution) / total_weight
        adaptive_weight_reasons = list(adaptive_weight_reasons or [])
        adaptive_weight_reasons.append("strategy_weight_bias")
    base_score = _weighted_average(
        [
            (signal_score, priority_weight_signal),
            (execution_score, priority_weight_execution),
        ]
    )
    penalties: list[str] = []
    penalty_total = 0.0
    if is_fallback:
        penalty_total += float(getattr(cfg, "FINAL_SCORE_PENALTY_FALLBACK", 0.20))
        penalties.append("fallback_penalty")
    if stale_quote:
        penalty_total += float(getattr(cfg, "FINAL_SCORE_PENALTY_STALE_QUOTE", 0.10))
        penalties.append("stale_quote_penalty")
    if missing_liquidity:
        penalty_total += float(getattr(cfg, "FINAL_SCORE_PENALTY_MISSING_LIQUIDITY", 0.08))
        penalties.append("missing_liquidity_penalty")
    if spread_uncertain:
        penalty_total += float(getattr(cfg, "FINAL_SCORE_PENALTY_SPREAD_UNCERTAINTY", 0.07))
        penalties.append("spread_uncertainty_penalty")
    if normalized_mode == "OFFHOURS":
        penalty_total += float(getattr(cfg, "FINAL_SCORE_PENALTY_OFFHOURS", 0.18))
        penalties.append("offhours_penalty")

    family_feedback_adjustment = max(
        -max_family_adjustment,
        min(max_family_adjustment, _safe_float(family_feedback.get("family_score_adjustment")) or 0.0),
    )
    family_survival_adjustment_max = max(
        0.0,
        float(getattr(cfg, "FINAL_SCORE_FAMILY_SURVIVAL_ADJUSTMENT_MAX", 0.05) or 0.05),
    )
    family_survival_adjustment = max(
        -family_survival_adjustment_max,
        min(
            family_survival_adjustment_max,
            (float(family_survival_component) - 0.5) * (family_survival_adjustment_max * 2.0),
        ),
    )
    strategy_weight_adjustment = max(
        -max_strategy_adjustment,
        min(max_strategy_adjustment, _safe_float(strategy_weight.get("strategy_weight_adjustment")) or 0.0),
    )
    bounded_risk_learning_adjustment = max(
        -float(getattr(cfg, "OFFLINE_RISK_LEARNING_MAX_ADJUSTMENT", 0.03) or 0.03),
        min(
            float(getattr(cfg, "OFFLINE_RISK_LEARNING_MAX_ADJUSTMENT", 0.03) or 0.03),
            (
                risk_learning_adjustment
                if risk_learning_adjustment is not None
                else (_safe_float(_candidate_value(candidate, "risk_learning_adjustment")) or 0.0)
            ),
        ),
    )
    bounded_risk_learning_confidence = _clamp01(
        risk_learning_confidence
        if risk_learning_confidence is not None
        else _safe_float(_candidate_value(candidate, "risk_learning_confidence")),
        default=0.0,
    )
    priority_score = _clamp01(
        base_score
        - penalty_total
        + float(family_feedback_adjustment)
        + float(strategy_weight_adjustment)
        + float(family_survival_adjustment)
        + float(bounded_risk_learning_adjustment),
        default=0.0,
    )
    adaptive_threshold_adjustment = apply_adaptive_thresholds(
        candidate,
        float(priority_score),
        market_mode=normalized_mode,
    )
    priority_score = _clamp01(
        float(adaptive_threshold_adjustment.get("adjusted_score") or priority_score),
        default=0.0,
    )
    class_cap_map = {
        "EXECUTABLE": float(getattr(cfg, "FINAL_SCORE_CLASS_CAP_EXECUTABLE", 1.0)),
        "NEAR_EXECUTABLE": float(getattr(cfg, "FINAL_SCORE_CLASS_CAP_NEAR_EXECUTABLE", 0.79)),
        "ADVISORY_ONLY": float(getattr(cfg, "FINAL_SCORE_CLASS_CAP_ADVISORY_ONLY", 0.49)),
    }
    class_cap = class_cap_map.get(normalized_class, class_cap_map["ADVISORY_ONLY"])
    final_score = min(priority_score, class_cap)
    return {
        "final_score": round(float(final_score), 6),
        "signal_score": round(float(signal_score), 6),
        "execution_score": round(float(execution_score), 6),
        "priority_score": round(float(priority_score), 6),
        "pre_cap_score": round(float(priority_score), 6),
        "base_score": round(float(base_score), 6),
        "class_cap": round(float(class_cap), 6),
        "penalty_total": round(float(penalty_total), 6),
        "penalty_reasons": penalties,
        "priority_weight_signal": round(float(priority_weight_signal), 6),
        "priority_weight_execution": round(float(priority_weight_execution), 6),
        "adaptive_weight_reasons": adaptive_weight_reasons,
        "setup_score": round(float(setup_component), 6),
        "trigger_score": round(float(trigger_component), 6),
        "entry_quality_score": round(float(entry_quality_component), 6),
        "family_survival_score": round(float(family_survival_component), 6),
        "family_survival_adjustment": round(float(family_survival_adjustment), 6),
        "family_feedback_adjustment": round(float(family_feedback_adjustment), 6),
        "family_feedback_confidence": round(float(_safe_float(family_feedback.get("family_confidence")) or 0.0), 6),
        "family_feedback_applied": bool(family_feedback.get("family_feedback_applied", False)),
        "family_signal_bias_adjustment": round(float(family_signal_bias_adjustment), 6),
        "family_execution_bias_adjustment": round(float(family_execution_bias_adjustment), 6),
        "expectancy_score": round(float(_safe_float(family_feedback.get("expectancy_score")) or 0.0), 6),
        "family_learning_state_generated_at": family_feedback.get("generated_at"),
        "family_learning_state_version": family_feedback.get("version"),
        "strategy_weight_adjustment": round(float(strategy_weight_adjustment), 6),
        "strategy_weight_confidence": round(float(_safe_float(strategy_weight.get("strategy_weight_confidence")) or 0.0), 6),
        "strategy_weight_applied": bool(strategy_weight.get("strategy_weight_applied", False)),
        "strategy_signal_bias_adjustment": round(float(strategy_signal_bias_adjustment), 6),
        "strategy_execution_bias_adjustment": round(float(strategy_execution_bias_adjustment), 6),
        "strategy_weight_state_generated_at": strategy_weight.get("generated_at"),
        "strategy_weight_state_version": strategy_weight.get("version"),
        "risk_learning_adjustment": round(float(bounded_risk_learning_adjustment), 6),
        "risk_learning_confidence": round(float(bounded_risk_learning_confidence), 6),
        "adaptive_threshold_adjustment": round(float(adaptive_threshold_adjustment.get("adaptive_threshold_adjustment") or 0.0), 6),
        "adaptive_threshold_impact_score": round(float(adaptive_threshold_adjustment.get("adaptive_threshold_impact_score") or 0.0), 6),
        "adaptive_threshold_applied": bool(adaptive_threshold_adjustment.get("adaptive_threshold_applied", False)),
        "adaptive_threshold_key": adaptive_threshold_adjustment.get("adaptive_threshold_key"),
        "adaptive_threshold_count": int(adaptive_threshold_adjustment.get("adaptive_threshold_count") or 0),
    }


def _latest_exec_quality():
    try:
        from core.fill_quality import get_latest_exec_quality
        return get_latest_exec_quality()
    except Exception:
        return None


def _adaptive_multiplier(strategy_name: str | None) -> float:
    if not strategy_name:
        return 1.0
    try:
        path = logs_dir() / "strategy_perf.json"
        if not path.exists():
            return 1.0
        raw = json.loads(path.read_text())
        stats = raw.get("stats", {})
        st = stats.get(strategy_name, {})
        trades = st.get("trades", 0)
        wins = st.get("wins", 0)
        if trades < 10:
            return 1.0
        win_rate = wins / max(1, trades)
        # Scale 0.8–1.2 around 50% win-rate
        mult = 0.8 + (win_rate - 0.5) * 0.8
        return max(0.6, min(1.2, mult))
    except Exception:
        return 1.0


def compute_confluence_score(score_pack: dict | None) -> float:
    """
    Deterministic confluence score in [0, 1] derived from score+alignment.
    """
    pack = score_pack or {}
    try:
        score = float(pack.get("score", 0.0) or 0.0)
    except Exception:
        score = 0.0
    try:
        alignment = float(pack.get("alignment", 0.0) or 0.0)
    except Exception:
        alignment = 0.0
    blended = (0.6 * score) + (0.4 * alignment)
    return max(0.0, min(1.0, blended / 100.0))


def compute_trade_score(market_data: dict, opt: dict, direction: str, rr: float | None, strategy_name: str | None = None):
    """
    Multi-factor trade scoring engine.
    Returns dict with score, alignment, components, and issues.
    """
    components = {}
    issues = []

    # Inputs
    ltp = market_data.get("ltp", 0) or 0
    vwap = market_data.get("vwap", ltp) or ltp
    htf_dir = (market_data.get("htf_dir") or "FLAT").upper()
    vwap_slope = market_data.get("vwap_slope", 0) or 0
    vol_z = market_data.get("vol_z", 0) or 0
    atr = market_data.get("atr", 0) or 0
    atr_pct = (atr / ltp) if ltp else 0
    day_type = (market_data.get("day_type") or "").upper()
    regime = (market_data.get("regime") or "").upper()
    shock_score = float(market_data.get("shock_score") or 0.0)
    uncertainty = float(market_data.get("uncertainty_index") or 0.0)
    macro_bias = float(market_data.get("macro_direction_bias") or 0.0)

    opt_ltp = opt.get("ltp") or 0
    bid = opt.get("bid") or 0
    ask = opt.get("ask") or 0
    spread_pct = (ask - bid) / opt_ltp if opt_ltp else 1
    volume = opt.get("volume", 0) or 0
    oi_build = (opt.get("oi_build") or "FLAT").upper()
    iv = opt.get("iv")
    iv_z = opt.get("iv_z")
    delta = opt.get("delta")
    theta = opt.get("theta")

    # 1) Trend alignment
    trend = 20
    if direction == "BUY_CALL":
        if ltp >= vwap and htf_dir == "UP" and vwap_slope >= 0:
            trend = 100
        elif ltp >= vwap:
            trend = 70
        elif htf_dir == "UP":
            trend = 50
    else:
        if ltp <= vwap and htf_dir == "DOWN" and vwap_slope <= 0:
            trend = 100
        elif ltp <= vwap:
            trend = 70
        elif htf_dir == "DOWN":
            trend = 50
    components["trend"] = trend

    # 2) Regime alignment
    if day_type in ("TREND_DAY", "RANGE_TREND_DAY", "TREND_RANGE_DAY"):
        regime_score = 90 if ((direction == "BUY_CALL" and htf_dir == "UP") or (direction == "BUY_PUT" and htf_dir == "DOWN")) else 60
    elif day_type in ("RANGE_DAY", "RANGE_VOLATILE"):
        regime_score = 40
        issues.append("Range day: directional risk")
    elif day_type in ("EVENT_DAY", "PANIC_DAY", "EXPIRY_DAY"):
        regime_score = 30
        issues.append("Event/expiry day risk")
    else:
        regime_score = 60
    components["regime"] = regime_score

    # 3) Risk/Reward
    if rr is None:
        rr_score = 0
        issues.append("RR missing")
    elif rr >= 2.0:
        rr_score = 100
    elif rr >= 1.5:
        rr_score = 70
    elif rr >= 1.2:
        rr_score = 50
    else:
        rr_score = 0
        issues.append("RR below 1.2")
    components["rr"] = rr_score

    # 4) Volatility context
    vol_score = 70
    if iv_z is not None and iv_z > 1.5:
        vol_score = 35
        issues.append("IV elevated")
    elif iv_z is not None and iv_z < -0.5:
        vol_score = 85
    if vol_z >= getattr(cfg, "EVENT_VOL_Z", 1.0):
        vol_score -= 15
        issues.append("High vol regime")
    if atr_pct >= getattr(cfg, "EVENT_ATR_PCT", 0.004):
        vol_score -= 10
    vol_score = max(0, min(100, vol_score))
    components["volatility"] = vol_score

    # 5) OI flow confirmation
    if direction == "BUY_CALL":
        if oi_build == "LONG":
            oi_score = 100
        elif oi_build == "SHORT_COVER":
            oi_score = 70
        elif oi_build == "FLAT":
            oi_score = 50
        else:
            oi_score = 25
    else:
        if oi_build == "SHORT":
            oi_score = 100
        elif oi_build == "LONG_LIQ":
            oi_score = 70
        elif oi_build == "FLAT":
            oi_score = 50
        else:
            oi_score = 25
    components["oi_flow"] = oi_score

    # 6) Liquidity
    if spread_pct <= 0.005 and volume >= 50000:
        liq = 100
    elif spread_pct <= getattr(cfg, "MAX_SPREAD_PCT", 0.015) and volume >= 10000:
        liq = 70
    elif spread_pct <= getattr(cfg, "MAX_SPREAD_PCT", 0.015):
        liq = 55
    else:
        liq = 30
        issues.append("Wide spread / low volume")
    components["liquidity"] = liq

    # 7) Multi-timeframe structure
    mtf = 40
    if direction == "BUY_CALL" and htf_dir == "UP" and ltp >= vwap:
        mtf = 90
    elif direction == "BUY_PUT" and htf_dir == "DOWN" and ltp <= vwap:
        mtf = 90
    elif htf_dir in ("UP", "DOWN"):
        mtf = 60
    components["mtf"] = mtf

    # 8) Event/news dampener
    if day_type in ("EVENT_DAY", "PANIC_DAY"):
        event_score = 30
    elif day_type == "EXPIRY_DAY":
        event_score = 40
    else:
        event_score = 100
    components["event"] = event_score

    # 9) News shock / macro bias
    news_score = 100.0
    news_score -= min(80.0, shock_score * 80.0)
    news_score -= min(30.0, uncertainty * 30.0)
    if shock_score >= getattr(cfg, "NEWS_SHOCK_EVENT_THRESHOLD", 0.4):
        issues.append("News shock elevated")
    if shock_score >= getattr(cfg, "NEWS_SHOCK_BLOCK_THRESHOLD", 0.7):
        news_score = 0.0
        issues.append("News shock extreme")
    bias_penalty = getattr(cfg, "NEWS_SHOCK_BIAS_PENALTY", 15)
    if macro_bias >= 0.2 and direction == "BUY_PUT":
        news_score -= bias_penalty
        issues.append("Macro bias bullish")
    if macro_bias <= -0.2 and direction == "BUY_CALL":
        news_score -= bias_penalty
        issues.append("Macro bias bearish")
    components["news_shock"] = max(0.0, min(100.0, news_score))

    # 10) Greeks sanity
    if delta is not None and (abs(delta) < getattr(cfg, "DELTA_MIN", 0.25) or abs(delta) > getattr(cfg, "DELTA_MAX", 0.7)):
        components["greeks"] = 40
        issues.append("Delta out of band")
    else:
        components["greeks"] = 80

    # Weighted score
    w = {
        "trend": 0.24,
        "regime": 0.15,
        "oi_flow": 0.15,
        "volatility": 0.10,
        "liquidity": 0.10,
        "rr": 0.10,
        "mtf": 0.08,
        "event": 0.03,
        "news_shock": 0.05,
    }
    score = 0.0
    for k, weight in w.items():
        score += weight * components.get(k, 0)

    # Optional cross-asset penalty (do not block)
    try:
        cross_q = market_data.get("cross_asset_quality", {}) or {}
        optional = set(getattr(cfg, "CROSS_OPTIONAL_FEEDS", []) or [])
        require_x = bool(getattr(cfg, "REQUIRE_CROSS_ASSET", True))
        if getattr(cfg, "REQUIRE_CROSS_ASSET_ONLY_WHEN_LIVE", True):
            live_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "LIVE"
            require_x = require_x and live_mode
        stale = set(cross_q.get("stale_feeds", []) or [])
        missing_map = cross_q.get("missing") or {}
        missing = set(k for k, v in missing_map.items() if not str(v).startswith("disabled"))
        bad_optional = (stale | missing) & optional
        if bad_optional:
            penalty = float(getattr(cfg, "CROSS_ASSET_OPTIONAL_SCORE_PENALTY", 8))
            score = max(0.0, score - penalty)
            issues.append("cross_asset_optional_stale" if require_x else "cross_asset_optional_warn")
    except Exception:
        pass

    # Execution quality influence
    try:
        exec_q = market_data.get("execution_quality_score")
        if exec_q is None:
            exec_q = _latest_exec_quality()
        if exec_q is not None:
            if float(exec_q) < float(getattr(cfg, "EXEC_QUALITY_BLOCK_BELOW", 35)):
                issues.append("exec_quality_block")
                score = 0.0
            elif float(exec_q) < float(getattr(cfg, "EXEC_QUALITY_MIN", 55)):
                penalty = float(getattr(cfg, "EXEC_QUALITY_PENALTY", 10))
                score = max(0.0, score - penalty)
                issues.append("exec_quality_low")
    except Exception:
        pass

    # Adaptive weighting (recent strategy performance)
    score *= _adaptive_multiplier(strategy_name)

    # Strategy alignment meter (trend + mtf + regime)
    alignment = (components["trend"] * 0.4) + (components["mtf"] * 0.3) + (components["regime"] * 0.3)

    result = {
        "score": max(0.0, min(100.0, score)),
        "alignment": max(0.0, min(100.0, alignment)),
        "components": components,
        "issues": issues,
        "day_type": day_type,
        "regime": regime,
    }
    result["confluence_score"] = compute_confluence_score(result)
    return result
