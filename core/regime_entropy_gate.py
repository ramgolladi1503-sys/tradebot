from __future__ import annotations

import logging
import math
from typing import Optional

from config import config as cfg
from core.regime_contract_v2 import (
    REGIME_LABELS,
    classify_entropy_state,
    probability_diagnostics,
)

logger = logging.getLogger(__name__)


def _threshold_for_context(
    *,
    session_bucket: str,
    expiry_day: bool,
    event_mode: bool,
) -> tuple[float, str]:
    if event_mode:
        return (
            float(getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_EVENT_MODE", 0.92)),
            "EVENT_MODE",
        )
    if expiry_day:
        return (
            float(getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_EXPIRY_DAY", 0.86)),
            "EXPIRY_DAY",
        )
    bucket = str(session_bucket or "DEFAULT").strip().upper()
    if bucket == "OPEN_DISCOVERY":
        return (
            float(getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_OPEN_DISCOVERY", 0.90)),
            "OPEN_DISCOVERY",
        )
    if bucket == "MID_SESSION":
        return (
            float(getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_MID_SESSION", 0.78)),
            "MID_SESSION",
        )
    if bucket == "CLOSING_VOL":
        return (
            float(getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_CLOSING_VOL", 0.88)),
            "CLOSING_VOL",
        )
    return (
        float(getattr(cfg, "REGIME_ENTROPY_NORMALIZED_MAX_DEFAULT", 0.80)),
        "DEFAULT",
    )


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
    """Canonical normalized-entropy gate.

    Low entropy is never a blocker by itself. Invalid probabilities, impossible
    raw entropy, insufficient feature quality, or entropy above the session
    threshold remain fail-closed.
    """
    reasons: list[str] = []
    invalid_probability_vector = False
    payload = market_data or {}

    count = int(regime_count or len(REGIME_LABELS))
    max_entropy = math.log(count) if count > 1 else 0.0
    probability_diag: dict = {}

    if probabilities:
        try:
            probability_diag = probability_diagnostics(probabilities)
            computed_raw = float(probability_diag["entropy"])
            computed_norm = float(probability_diag["normalized_entropy"])
        except ValueError as exc:
            invalid_probability_vector = True
            reasons.append(f"invalid_probability_vector:{exc}")
            computed_raw = max_entropy
            computed_norm = 1.0
    else:
        try:
            computed_raw = float(raw_entropy) if raw_entropy is not None else 0.0
        except (TypeError, ValueError):
            computed_raw = -1.0
        computed_norm = (
            computed_raw / max_entropy
            if max_entropy > 0.0 and computed_raw > 0.0
            else 0.0
        )
        computed_norm = min(max(computed_norm, 0.0), 1.0)

    threshold, threshold_source = _threshold_for_context(
        session_bucket=session_bucket,
        expiry_day=expiry_day,
        event_mode=event_mode,
    )

    # Compatibility only for legacy callers that provide raw entropy without a
    # probability vector. Real probability decisions do not relax uncertainty
    # based on the classifier's own primary label because that is circular.
    resolved_regime = str(
        primary_regime
        or payload.get("primary_regime")
        or payload.get("regime")
        or ""
    ).upper()
    legacy_raw_only = not bool(probabilities) and raw_entropy is not None
    if legacy_raw_only and resolved_regime in {
        "RANGE",
        "RANGE_VOLATILE",
        "SIDEWAYS",
    }:
        threshold = 1.0
        threshold_source += "_LEGACY_RAW_RANGE_OVERRIDE"

    threshold = min(max(float(threshold), 0.0), 1.0)
    uncertain = bool(computed_norm > threshold)

    if computed_raw < 0.0:
        reasons.append(f"raw_entropy_negative:{computed_raw:.6f}")
        uncertain = True
    elif max_entropy > 0.0 and computed_raw > max_entropy + 1e-6:
        reasons.append(
            "raw_entropy_exceeds_theoretical_max:"
            f"{computed_raw:.6f}>{max_entropy:.6f}"
        )
        uncertain = True

    feature_quality_status = str(
        payload.get("feature_quality_status") or ""
    ).upper()
    if feature_quality_status in {"INSUFFICIENT_DATA", "INVALID_INPUT"}:
        reasons.append(f"feature_quality:{feature_quality_status.lower()}")
        uncertain = True

    if invalid_probability_vector:
        uncertain = True

    entropy_state = classify_entropy_state(computed_norm, threshold)
    low_entropy_suspect = bool(
        computed_norm <= 0.01
        and feature_quality_status in {"INSUFFICIENT_DATA", "INVALID_INPUT"}
    )
    if low_entropy_suspect:
        reasons.append("low_entropy_with_invalid_feature_quality")
        uncertain = True

    if uncertain and computed_norm > threshold:
        reasons.append(
            f"entropy_above_limit:{computed_norm:.6f}>"
            f"{threshold:.6f}@{threshold_source}"
        )

    top_probability = probability_diag.get("top_probability")
    if top_probability is None and regime_prob_max is not None:
        try:
            top_probability = float(regime_prob_max)
        except (TypeError, ValueError):
            top_probability = None

    return {
        "uncertain": bool(uncertain),
        "gate_passed": not bool(uncertain),
        "raw_entropy": computed_raw,
        "max_entropy": max_entropy,
        "normalized_entropy": computed_norm,
        "entropy_state": entropy_state,
        "low_entropy_suspect": low_entropy_suspect,
        "threshold": threshold,
        "threshold_source": threshold_source,
        "probability_valid": not invalid_probability_vector,
        "top_probability": top_probability,
        "second_probability": probability_diag.get("second_probability"),
        "top_two_margin": probability_diag.get("top_two_margin"),
        "diagnostics": {
            "source": threshold_source,
            "max_entropy": max_entropy,
            "computed_raw": computed_raw,
            "computed_norm": computed_norm,
            "threshold": threshold,
            "feature_quality_status": feature_quality_status or None,
            "primary_regime": resolved_regime or None,
            "reasons": list(dict.fromkeys(reasons)),
        },
    }
