from __future__ import annotations

import pandas as pd

from research.macd_futures_participation_regime_v1.analysis import CampaignBlocked

MIN_COMPATIBLE_PLACEBOS_PER_SIGNAL = 20


def validate_state_matching_coverage(
    per_signal: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    minimum_compatible: int = MIN_COMPATIBLE_PLACEBOS_PER_SIGNAL,
) -> dict:
    """Require complete signal coverage after futures-state placebo filtering.

    This gate is intentionally evaluated before interpreting subgroup expectancy.
    A signal may not silently disappear because it had no same-state placebo,
    and a signal with only a handful of compatible placebo origins is not treated
    as adequately matched.
    """
    if "signal_trade_id" not in per_signal.columns:
        raise CampaignBlocked("MATCHING_PER_SIGNAL_ID_MISSING")
    if "compatible_placebo_n" not in per_signal.columns:
        raise CampaignBlocked("MATCHING_COMPATIBLE_N_MISSING")
    if "signal_trade_id" not in signals.columns:
        raise CampaignBlocked("MATCHING_SIGNAL_ID_MISSING")

    expected = set(signals["signal_trade_id"].astype(str))
    observed = set(per_signal["signal_trade_id"].astype(str))
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    if unexpected:
        raise CampaignBlocked(
            f"STATE_MATCH_UNEXPECTED_SIGNALS:{len(unexpected)}:{','.join(unexpected[:10])}"
        )
    if missing:
        raise CampaignBlocked(
            f"STATE_MATCH_ZERO_COMPATIBLE_PLACEBOS:{len(missing)}:{','.join(missing[:10])}"
        )

    counts = pd.to_numeric(per_signal["compatible_placebo_n"], errors="coerce")
    if counts.isna().any():
        raise CampaignBlocked("STATE_MATCH_INVALID_COMPATIBLE_COUNTS")
    min_count = int(counts.min()) if len(counts) else 0
    below = int((counts < minimum_compatible).sum())
    if below:
        raise CampaignBlocked(
            "STATE_MATCH_INSUFFICIENT_COMPATIBLE_PLACEBOS:"
            f"signals_below={below}:min={min_count}:required={minimum_compatible}"
        )

    return {
        "expected_signal_count": int(len(expected)),
        "represented_signal_count": int(len(observed)),
        "signal_coverage_fraction": 1.0,
        "minimum_compatible_placebos_required": int(minimum_compatible),
        "minimum_compatible_placebos_observed": min_count,
        "median_compatible_placebos_observed": float(counts.median()),
        "matching_coverage_gate": "PASS",
        "outcome_threshold_tuned": False,
    }
