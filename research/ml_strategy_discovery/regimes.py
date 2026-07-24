from __future__ import annotations

import numpy as np
import pandas as pd


def classify_deterministic_regimes(features: pd.DataFrame) -> pd.DataFrame:
    required = {
        "directional_efficiency_10",
        "trend_slope_10_atr",
        "atr_pct_63",
        "gap_pct",
        "minutes_since_open",
    }
    missing = required.difference(features.columns)
    if missing:
        raise ValueError(f"missing regime inputs: {sorted(missing)}")

    output = pd.DataFrame(index=features.index)
    efficiency = features["directional_efficiency_10"]
    slope = features["trend_slope_10_atr"]
    output["trend_regime"] = np.select(
        [
            (efficiency >= 0.55) & (slope > 0.05),
            (efficiency >= 0.55) & (slope < -0.05),
            efficiency <= 0.30,
        ],
        [1.0, -1.0, 0.0],
        default=np.nan,
    )
    output["volatility_regime"] = np.select(
        [features["atr_pct_63"] >= 0.75, features["atr_pct_63"] <= 0.25],
        [1.0, -1.0],
        default=0.0,
    )
    absolute_gap = features["gap_pct"].abs()
    output["gap_regime"] = np.select(
        [absolute_gap >= 0.01, absolute_gap >= 0.003],
        [2.0, 1.0],
        default=0.0,
    )
    output["time_regime"] = np.select(
        [features["minutes_since_open"] <= 60, features["minutes_since_open"] <= 240],
        [0.0, 1.0],
        default=2.0,
    )
    return output
