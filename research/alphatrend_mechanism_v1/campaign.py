"""Development-only campaign for the transparent AlphaTrend-inspired mechanism."""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from .engine import (
    AlphaTrendMechanismConfig,
    SIGNAL_COLUMNS,
    add_forward_labels,
    build_features,
    build_negative_controls,
    evaluate_signal,
)
from .independence import evaluate_nonoverlap

HORIZONS = (5, 10, 15, 20, 30)

PREDECLARED_CONFIGS: dict[str, AlphaTrendMechanismConfig] = {
    "AT_M1_BASE": AlphaTrendMechanismConfig(),
    "AT_M1_FAST": AlphaTrendMechanismConfig(
        fast_span=5,
        slow_span=13,
        momentum_spans=(2, 3, 5, 8, 13, 21),
        pivot_left=1,
        pivot_right=1,
        fresh_trend_max_age_bars=21,
    ),
    "AT_M1_SLOW": AlphaTrendMechanismConfig(
        fast_span=13,
        slow_span=34,
        momentum_spans=(5, 8, 13, 21, 34, 55),
        fresh_trend_max_age_bars=55,
    ),
    "AT_M1_STRUCTURE_FAST": AlphaTrendMechanismConfig(
        pivot_left=1,
        pivot_right=1,
    ),
    "AT_M1_PULLBACK_TIGHT": AlphaTrendMechanismConfig(
        pullback_buffer_atr=0.10,
    ),
    "AT_M1_PULLBACK_WIDE": AlphaTrendMechanismConfig(
        pullback_buffer_atr=0.30,
    ),
}


def run_development_campaign(
    bars: pd.DataFrame,
    *,
    horizons: Iterable[int] = HORIZONS,
    control_shift_bars: int = 17,
) -> dict[str, object]:
    """Evaluate only the predeclared family on caller-supplied development bars."""
    hs = tuple(sorted({int(h) for h in horizons}))
    if 15 not in hs or 30 not in hs:
        raise ValueError("development campaign requires 15- and 30-bar horizons")

    variants: dict[str, object] = {}
    for config_id, cfg in PREDECLARED_CONFIGS.items():
        featured = build_features(bars, cfg)
        labeled = add_forward_labels(featured, hs)
        metrics = {
            signal: evaluate_signal(labeled, signal, hs)
            for signal in SIGNAL_COLUMNS
        }
        effective_samples = {
            signal: evaluate_nonoverlap(labeled, signal, (15, 30))
            for signal in SIGNAL_COLUMNS
        }

        controls: dict[str, object] = {}
        for signal in ("signal_full_fresh", "signal_continuation"):
            control_frame = build_negative_controls(
                labeled,
                signal,
                shift_bars=control_shift_bars,
            )
            inverse = f"{signal}__control_inverse"
            shifted = f"{signal}__control_shift_{control_shift_bars}"
            controls[signal] = {
                "inverse": evaluate_signal(control_frame, inverse, hs),
                "shifted": evaluate_signal(control_frame, shifted, hs),
                "inverse_nonoverlap": evaluate_nonoverlap(control_frame, inverse, (15, 30)),
                "shifted_nonoverlap": evaluate_nonoverlap(control_frame, shifted, (15, 30)),
            }

        variants[config_id] = {
            "config": cfg.to_dict(),
            "metrics": metrics,
            "effective_samples": effective_samples,
            "controls": controls,
            "screen": {
                "fresh": _screen(metrics, controls, effective_samples, "signal_full_fresh"),
                "continuation": _screen(metrics, controls, effective_samples, "signal_continuation"),
            },
        }

    return {
        "schema_version": 2,
        "campaign": "ALPHATREND_INSPIRED_MECHANISM_DEV_V1",
        "scope": "DEVELOPMENT_ONLY",
        "proprietary_equivalence_claimed": False,
        "option_pnl_claimed": False,
        "holdout_evaluated": False,
        "validation_evaluated": False,
        "parameter_family_predeclared": True,
        "overlap_adjustment": "GREEDY_SAME_SESSION_NONOVERLAP_BY_HORIZON",
        "variants": variants,
    }


def _screen(
    metrics: dict[str, dict[str, object]],
    controls: dict[str, object],
    effective_samples: dict[str, dict[str, object]],
    signal: str,
) -> dict[str, object]:
    candidate = metrics[signal]
    candidate_effective = effective_samples[signal]
    baseline_effective = effective_samples["signal_trend_only"]
    inverse_effective = controls[signal]["inverse_nonoverlap"]
    shifted_effective = controls[signal]["shifted_nonoverlap"]
    reasons: list[str] = []

    # Raw events are reported, but screening uses the conservative 30-bar
    # non-overlapping sample so dense events inside one trend cannot masquerade
    # as independent evidence.
    effective_30 = candidate_effective["horizons"]["30"]
    if int(effective_30["nonoverlap_n"]) < 100:
        reasons.append("NONOVERLAP_30_EVENTS_LT_100")
    if int(effective_30["sessions"]) < 20:
        reasons.append("NONOVERLAP_30_SESSIONS_LT_20")

    for horizon in ("15", "30"):
        c = candidate_effective["horizons"][horizon]
        b = baseline_effective["horizons"][horizon]
        inv = inverse_effective["horizons"][horizon]
        sh = shifted_effective["horizons"][horizon]
        c_mean = _number(c["mean_directional_bps"])
        c_median = _number(c["median_directional_bps"])
        b_mean = _number(b["mean_directional_bps"])
        inv_mean = _number(inv["mean_directional_bps"])
        sh_mean = _number(sh["mean_directional_bps"])
        max_session_share = _number(c["max_session_event_share"])
        max_month_share = _number(c["max_month_event_share"])

        if c_mean is None or c_mean <= 0:
            reasons.append(f"NONOVERLAP_MEAN_{horizon}_NOT_POSITIVE")
        if c_median is None or c_median < 0:
            reasons.append(f"NONOVERLAP_MEDIAN_{horizon}_NEGATIVE")
        if c_mean is None or b_mean is None or c_mean <= b_mean:
            reasons.append(f"NO_INCREMENT_OVER_TREND_{horizon}")
        if inv_mean is None or inv_mean >= 0:
            reasons.append(f"INVERSE_CONTROL_{horizon}_NOT_NEGATIVE")
        if (
            c_mean is not None
            and c_mean > 0
            and sh_mean is not None
            and sh_mean >= 0.75 * c_mean
        ):
            reasons.append(f"SHIFT_CONTROL_{horizon}_RETAINS_GE_75PCT")
        if max_session_share is not None and max_session_share > 0.20:
            reasons.append(f"SESSION_CONCENTRATION_{horizon}_GT_20PCT")
        if max_month_share is not None and max_month_share > 0.35:
            reasons.append(f"MONTH_CONCENTRATION_{horizon}_GT_35PCT")

    unique_reasons = sorted(set(reasons))
    return {
        "status": "DEVELOPMENT_SCREEN_PASS" if not unique_reasons else "DEVELOPMENT_SCREEN_FAIL",
        "reasons": unique_reasons,
        "raw_event_count": int(candidate["events"]),
        "effective_nonoverlap_30_count": int(effective_30["nonoverlap_n"]),
        "promotion_authorized": False,
    }


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["HORIZONS", "PREDECLARED_CONFIGS", "run_development_campaign"]
