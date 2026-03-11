"""Migration note:
Regime-aware trade permission engine to damp signal confidence and
control EXECUTE / QUEUE_ONLY / ADVISORY_ONLY / BLOCK surfaces.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from config import config as cfg


class Permission(str, Enum):
    EXECUTE = "EXECUTE"
    QUEUE_ONLY = "QUEUE_ONLY"
    ADVISORY_ONLY = "ADVISORY_ONLY"
    BLOCK = "BLOCK"


def clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return float(lo)
    if value > hi:
        return float(hi)
    return float(value)


def _norm_text(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_execution_mode(execution_mode: str | None) -> str:
    mode = _norm_text(execution_mode or getattr(cfg, "EXECUTION_MODE", "SIM"))
    if mode in {"LIVE", "PAPER", "SIM", "OFFHOURS", "PLANNING", "ADVISORY"}:
        return mode
    return "SIM"


def resolve_confidence_thresholds(execution_mode: str | None = None) -> dict[str, float]:
    mode = normalize_execution_mode(execution_mode)
    display_threshold = clamp(float(getattr(cfg, "CONFIDENCE_THRESHOLD_DISPLAY", 0.0)), 0.0, 1.0)
    advisory_threshold = clamp(float(getattr(cfg, "CONFIDENCE_THRESHOLD_ADVISORY", 0.15)), 0.0, 1.0)
    live_threshold = clamp(
        float(getattr(cfg, "CONFIDENCE_THRESHOLD_EXECUTION_LIVE", 0.30)),
        0.0,
        1.0,
    )
    paper_threshold = clamp(
        float(getattr(cfg, "CONFIDENCE_THRESHOLD_EXECUTION_PAPER", 0.27)),
        0.0,
        1.0,
    )
    sim_threshold = clamp(
        float(getattr(cfg, "CONFIDENCE_THRESHOLD_EXECUTION_SIM", paper_threshold)),
        0.0,
        1.0,
    )
    execution_threshold = live_threshold
    if mode in {"PAPER", "PLANNING", "OFFHOURS", "ADVISORY"}:
        execution_threshold = paper_threshold
    elif mode == "SIM":
        execution_threshold = sim_threshold
    advisory_threshold = min(advisory_threshold, execution_threshold)
    display_threshold = min(display_threshold, advisory_threshold)
    return {
        "mode": mode,
        "display": float(display_threshold),
        "advisory": float(advisory_threshold),
        "execution": float(execution_threshold),
    }


def classify_confidence_vs_threshold(
    global_conf: float | None,
    *,
    execution_mode: str | None = None,
    hard_blocker: bool = False,
    entry_blocked: bool = False,
) -> str:
    if hard_blocker:
        return "hard_blocker_overrides_threshold"
    if entry_blocked:
        return "entry_blocker_overrides_threshold"
    if global_conf is None:
        return "confidence_missing"
    thresholds = resolve_confidence_thresholds(execution_mode)
    if global_conf < thresholds["display"]:
        return "below_display_threshold"
    if global_conf < thresholds["advisory"]:
        return "below_advisory_threshold"
    if global_conf < thresholds["execution"]:
        return "meets_advisory_below_execution_threshold"
    return "meets_execution_threshold"


def normalize_orb_bias(orb_bias: str | None) -> str:
    text = _norm_text(orb_bias)
    if text in {"UP", "BULLISH"}:
        return "BULLISH"
    if text in {"DOWN", "BEARISH"}:
        return "BEARISH"
    if text in {"NEUTRAL", "PENDING"}:
        return "NEUTRAL"
    if not text:
        return "UNKNOWN"
    return text


def derive_direction(option_type: str | None, side: str | None) -> str:
    opt = _norm_text(option_type)
    side_norm = _norm_text(side)
    if opt in {"CE", "CALL"} and side_norm == "BUY":
        return "BULLISH"
    if opt in {"PE", "PUT"} and side_norm == "BUY":
        return "BEARISH"
    if opt in {"CE", "CALL"} and side_norm == "SELL":
        return "BEARISH"
    if opt in {"PE", "PUT"} and side_norm == "SELL":
        return "BULLISH"
    return "UNKNOWN"


def orb_alignment_multiplier(orb_bias: str | None, direction: str | None) -> float:
    orb = normalize_orb_bias(orb_bias)
    dir_norm = _norm_text(direction)
    if orb in {"UNKNOWN", ""}:
        return 0.65
    if orb == "NEUTRAL" or dir_norm in {"", "UNKNOWN"}:
        return 0.75
    if (orb == "BULLISH" and dir_norm == "BULLISH") or (orb == "BEARISH" and dir_norm == "BEARISH"):
        return 1.0
    return 0.50


def regime_penalty(regime: str | None) -> float:
    reg = _norm_text(regime)
    if reg == "VOLATILE":
        return 0.70
    if reg == "UNKNOWN":
        return 0.60
    return 1.0


def compute_global_conf(
    signal_score: float,
    regime: str | None,
    regime_conf: float,
    orb_bias: str | None,
    direction: str | None,
) -> float:
    base = clamp(float(signal_score), 0.0, 1.0)
    regime_factor = clamp(float(regime_conf), 0.15, 1.0)
    orb_factor = orb_alignment_multiplier(orb_bias, direction)
    reg_pen = regime_penalty(regime)
    global_conf = base * regime_factor * orb_factor * reg_pen
    return round(float(global_conf), 3)


def is_countertrend(regime: str | None, direction: str | None) -> bool:
    reg = _norm_text(regime)
    dir_norm = _norm_text(direction)
    if reg == "TREND_UP" and dir_norm == "BEARISH":
        return True
    if reg == "TREND_DOWN" and dir_norm == "BULLISH":
        return True
    return False


def decide_permission(
    global_conf: float,
    regime: str | None,
    regime_conf: float,
    direction: str | None,
    orb_bias: str | None,
    execution_mode: str | None = None,
) -> tuple[str, str]:
    reg = _norm_text(regime)
    thresholds = resolve_confidence_thresholds(execution_mode)
    if reg == "UNKNOWN" and float(regime_conf) < 0.35:
        return (Permission.ADVISORY_ONLY.value, "unknown_regime_low_conf")
    if global_conf < thresholds["advisory"]:
        return (Permission.ADVISORY_ONLY.value, "low_global_conf")
    if global_conf < thresholds["execution"]:
        return (Permission.QUEUE_ONLY.value, "medium_global_conf")
    if is_countertrend(regime, direction):
        return (Permission.QUEUE_ONLY.value, "countertrend_high_conf")
    return (Permission.EXECUTE.value, "aligned_high_conf")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def normalize_signal_score(signal_score: float | None) -> float:
    """
    Normalize signal score to [0, 1] exactly once.

    Accepted input ranges:
    - [0, 1] -> unchanged
    - (1, 100] -> interpreted as percentage score and divided by 100
    - otherwise -> clamped to [0, 1]
    """
    raw = _safe_float(signal_score)
    if raw is None:
        return 0.0
    if 0.0 <= raw <= 1.0:
        return float(raw)
    if 1.0 < raw <= 100.0:
        return float(raw / 100.0)
    return clamp(float(raw), 0.0, 1.0)


def apply_bearish_impulse_guard(
    permission: str,
    reason: str,
    *,
    direction: str | None,
    last_candle: dict[str, Any] | None = None,
    atr_ratio: float | None = None,
) -> tuple[str, str]:
    if not bool(getattr(cfg, "PERMISSION_IMPULSE_ENABLE", True)):
        return permission, reason
    if _norm_text(direction) != "BULLISH":
        return permission, reason
    if not isinstance(last_candle, dict):
        return permission, reason
    open_px = _safe_float(last_candle.get("open"))
    close_px = _safe_float(last_candle.get("close"))
    if open_px is None or close_px is None or open_px <= 0:
        return permission, reason
    if close_px >= open_px:
        return permission, reason
    body = abs(close_px - open_px)
    body_pct = body / open_px if open_px > 0 else 0.0
    body_threshold = float(getattr(cfg, "PERMISSION_IMPULSE_BODY_PCT", 0.006))
    atr_mult = float(getattr(cfg, "PERMISSION_IMPULSE_ATR_MULT", 1.0))
    atr_val = _safe_float(last_candle.get("atr"))
    if atr_val is None and atr_ratio is not None:
        atr_val = abs(open_px) * float(atr_ratio)
    atr_hit = atr_val is not None and body >= (atr_mult * atr_val)
    if body_pct < body_threshold and not atr_hit:
        return permission, reason
    if permission == Permission.EXECUTE.value:
        return Permission.QUEUE_ONLY.value, "bearish_impulse_cooldown"
    if permission == Permission.QUEUE_ONLY.value:
        return Permission.ADVISORY_ONLY.value, "bearish_impulse_cooldown"
    return permission, reason


def build_permission_payload(
    *,
    signal_score: float | None,
    regime: str | None,
    regime_conf: float | None,
    orb_bias: str | None,
    option_type: str | None,
    side: str | None,
    execution_mode: str | None = None,
    last_candle: dict[str, Any] | None = None,
    atr_ratio: float | None = None,
) -> dict[str, Any]:
    base_score = normalize_signal_score(signal_score)
    reg_conf = _safe_float(regime_conf)
    reg_conf_for_calc = 0.0 if reg_conf is None else float(reg_conf)
    direction = derive_direction(option_type, side)
    thresholds = resolve_confidence_thresholds(execution_mode)
    orb_factor = orb_alignment_multiplier(orb_bias, direction)
    reg_pen = regime_penalty(regime)
    global_conf = compute_global_conf(
        base_score,
        regime=regime,
        regime_conf=reg_conf_for_calc,
        orb_bias=orb_bias,
        direction=direction,
    )
    if reg_conf is None:
        permission, reason = (Permission.ADVISORY_ONLY.value, "missing_regime_conf")
    else:
        permission, reason = decide_permission(
            global_conf,
            regime=regime,
            regime_conf=reg_conf,
            direction=direction,
            orb_bias=orb_bias,
            execution_mode=thresholds["mode"],
        )
    permission, reason = apply_bearish_impulse_guard(
        permission,
        reason,
        direction=direction,
        last_candle=last_candle,
        atr_ratio=atr_ratio,
    )
    return {
        "direction": direction,
        "global_confidence": global_conf,
        "permission": permission,
        "permission_reason": reason,
        "countertrend": bool(is_countertrend(regime, direction)),
        "orb_bias": normalize_orb_bias(orb_bias),
        "signal_score": float(base_score),
        "orb_factor": float(orb_factor),
        "regime_penalty": float(reg_pen),
        "regime_confidence": reg_conf,
        "threshold_display": float(thresholds["display"]),
        "threshold_advisory": float(thresholds["advisory"]),
        "threshold_execution": float(thresholds["execution"]),
        "confidence_vs_threshold_reason": classify_confidence_vs_threshold(
            global_conf,
            execution_mode=thresholds["mode"],
        ),
    }
