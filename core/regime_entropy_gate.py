import math
import logging
from typing import Optional

from config import config as cfg
from core.entropy_contract import entropy_diagnostics
from core.regime_prob_model import REGIMES

logger = logging.getLogger(__name__)

def evaluate_regime_entropy_gate(
    raw_entropy: Optional[float] = None,
    probabilities: Optional[dict] = None,
    regime_count: Optional[int] = None,
    session_bucket: str = "DEFAULT",
    expiry_day: bool = False,
    event_mode: bool = False,
    market_data: Optional[dict] = None,
    primary_regime: str = "",
    regime_prob_max: Optional[float] = None,
) -> dict:
    """
    Central gate to determine if market regime entropy exceeds bounds.
    Removes raw_entropy thresholds from legacy codebase paths.
    """
    diag_reasons = []
    invalid_probability_vector = False

    count = regime_count or len(REGIMES)
    max_entropy = math.log(count) if count > 0 else 1.0

    if probabilities:
        try:
            diag = entropy_diagnostics(probabilities, labels=REGIMES if not regime_count else None)
            computed_raw = diag.get("entropy", 0.0)
            computed_norm = diag.get("normalized_entropy", 0.0)
        except ValueError as e:
            invalid_probability_vector = True
            diag_reasons.append(f"invalid_probability_vector: {str(e)}")
            computed_raw = 999.0
            computed_norm = 1.0
    else:
        computed_raw = raw_entropy if raw_entropy is not None else 0.0
        if computed_raw > 0 and max_entropy > 0:
            computed_norm = computed_raw / max_entropy
        else:
            computed_norm = 0.0

    # Safety clamp
    computed_norm = min(max(computed_norm, 0.0), 1.0)

    # Determine thresholds based on config and session bounds
    if event_mode:
        threshold = float(getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_EVENT_MODE", 0.92))
        threshold_source = "EVENT_MODE"
    elif expiry_day:
        threshold = float(getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_EXPIRY_DAY", 0.86))
        threshold_source = "EXPIRY_DAY"
    else:
        sb = str(session_bucket).upper()
        if sb == "OPEN_DISCOVERY":
            threshold = float(getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_OPEN_DISCOVERY", 0.90))
            threshold_source = "OPEN_DISCOVERY"
        elif sb == "MID_SESSION":
            threshold = float(getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_MID_SESSION", 0.78))
            threshold_source = "MID_SESSION"
        elif sb == "CLOSING_VOL":
            threshold = float(getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_CLOSING_VOL", 0.88))
            threshold_source = "CLOSING_VOL"
        else:
            threshold = float(getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_DEFAULT", 0.80))
            threshold_source = "DEFAULT"

    md = market_data or {}
    depth_imb = float(md.get("depth_imbalance") or 0.0)
    volume_delta = bool(md.get("volume_delta_override") or False)
    
    if regime_prob_max is not None:
        prob_max = float(regime_prob_max)
    else:
        prob_max = float(md.get("regime_prob_max") or md.get("regime_probs_max") or 0.0)
        
    resolved_regime = primary_regime or md.get("primary_regime") or md.get("regime") or ""

    if resolved_regime == "TREND" and (volume_delta or depth_imb > 0.35 or prob_max > 0.60):
        threshold *= 1.30
        threshold_source += "_TREND_OVERRIDE"

    # Dynamic Entropy Override for Ranging Regimes
    if resolved_regime in {"RANGE", "RANGE_VOLATILE", "SIDEWAYS"}:
        threshold *= 2.0
        threshold_source += "_RANGE_OVERRIDE"

    # Safety clamp for threshold
    threshold = min(max(threshold, 0.0), 1.0)

    uncertain = bool(computed_norm > threshold)

    diagnostics = []
    if computed_raw > max_entropy + 0.001:
        diagnostics.append(f"raw_entropy ({computed_raw:.4f}) exceeded max theoretical bound ({max_entropy:.4f})")
        uncertain = True
    elif computed_raw < 0:
        diagnostics.append(f"raw_entropy ({computed_raw:.4f}) is negative")
        uncertain = True

    if uncertain:
        diagnostics.append(f"market_regime_uncertain=True (norm {computed_norm:.4f} > limit {threshold:.4f} @ {threshold_source})")
        
    if invalid_probability_vector:
        is_uncertain = True
    else:
        is_uncertain = uncertain

    return {
        "uncertain": is_uncertain,
        "raw_entropy": computed_raw,
        "max_entropy": max_entropy,
        "normalized_entropy": computed_norm,
        "threshold": threshold,
        "threshold_source": threshold_source,
        "probability_valid": not invalid_probability_vector,
        "diagnostics": {
            "source": threshold_source,
            "max_entropy": max_entropy,
            "computed_raw": computed_raw,
            "computed_norm": computed_norm,
            "threshold": threshold,
            "reasons": diag_reasons,
        }
    }
