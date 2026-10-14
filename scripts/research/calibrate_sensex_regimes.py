"""Empirical SENSEX Multi-Regime Calibrator.

Analyzes 442,677 1-minute SENSEX bars (Jan 2022 - Oct 2026) from:
/Volumes/TradeBot/historical/sensex/sensex_1minute_2022_2026.parquet

Preserves trading safety invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False

Calibrates mathematical boundaries for Canonical Regimes:
1. RANGE / COMPRESSION
2. TRENDING_UP
3. TRENDING_DOWN
4. VOLATILE / SHOCK

Extracts:
- Historical Occurrence %
- Optimal Take-Profit & Stop-Loss targets
- Kaufman Efficiency Ratio (KER) thresholds
- Opening Range distributions & Macro Exhaustion Caps
- Saves frozen calibration matrix to artifacts/sensex_calibrated_regime_matrix.json
"""

import json
import os
from pathlib import Path
import numpy as np
import pandas as pd


def calibrate_sensex(parquet_path: str, out_matrix_path: str):
    print(f"📊 [SENSEX CALIBRATOR] Loading historical archive: {parquet_path}...")
    df_raw = pd.read_parquet(parquet_path)
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
    df_raw = df_raw.sort_values("timestamp").reset_index(drop=True)
    total_bars = len(df_raw)
    print(f"✅ Loaded {total_bars:,} bars spanning {df_raw['timestamp'].iloc[0]} to {df_raw['timestamp'].iloc[-1]}")

    # Group by date to process sessions causally with session-isolated VWAP & OR
    df_raw["date"] = df_raw["timestamp"].dt.date
    dates = df_raw["date"].unique()
    print(f"🗓️ Total Trading Sessions: {len(dates):,}")

    all_slices = []
    session_or_widths = []
    session_ranges = []

    for d in dates:
        day_df = df_raw[df_raw["date"] == d].copy().reset_index(drop=True)
        if len(day_df) < 60:
            continue

        close = day_df["close"].values
        high = day_df["high"].values
        low = day_df["low"].values
        times = day_df["timestamp"].dt.time.values

        # Compute intraday VWAP
        # Since BSE Index volume is 0 or synthetic, use typical price running EWMA/mean
        typ = (high + low + close) / 3.0
        vwap = np.cumsum(typ) / (np.arange(len(typ)) + 1)

        # Opening Range: 09:15 - 09:45 (first 30 bars)
        or_mask = times <= pd.to_datetime("09:45:00").time()
        if np.any(or_mask):
            or_high = np.max(high[or_mask])
            or_low = np.min(low[or_mask])
            or_width = or_high - or_low
            session_or_widths.append(or_width)

        # Full day range
        session_ranges.append(np.max(high) - np.min(low))

        # Sliding 20-bar causal windows for regime classification
        for i in range(20, len(day_df) - 15):
            window_close = close[i-20:i]
            net_change = window_close[-1] - window_close[0]
            gross_path = np.sum(np.abs(np.diff(window_close)))

            # Kaufman Efficiency Ratio (KER: 0.0 to 1.0)
            er = abs(net_change) / gross_path if gross_path > 0 else 0.0

            # Distance from VWAP
            vwap_dist = close[i] - vwap[i]

            # Volatility: average 1m bar range in window
            avg_bar_range = np.mean(high[i-20:i] - low[i-20:i])

            # Forward realization across next 15 bars (~15 min hold horizon)
            fwd_high = np.max(high[i:i+15]) - close[i]
            fwd_low = close[i] - np.min(low[i:i+15])
            fwd_net = close[i+14] - close[i]

            all_slices.append({
                "er": er,
                "vwap_dist": vwap_dist,
                "avg_range": avg_bar_range,
                "net_change": net_change,
                "fwd_high": fwd_high,
                "fwd_low": fwd_low,
                "fwd_net": fwd_net,
                "bar_range": high[i] - low[i],
            })

    df_metrics = pd.DataFrame(all_slices)
    print(f"🔍 Extracted {len(df_metrics):,} causal sliding windows across {len(dates)} sessions.")

    # Empirical Distributions of SENSEX Metrics
    median_bar_range = float(df_metrics["avg_range"].median())
    p90_bar_range = float(df_metrics["avg_range"].quantile(0.90))
    p90_or_width = float(np.percentile(session_or_widths, 90))
    p90_session_range = float(np.percentile(session_ranges, 90))

    print(f"\n📈 [SENSEX MICROSTRUCTURE REALITIES]")
    print(f"   Median 1m Bar Range: {median_bar_range:.1f} pts")
    print(f"   90th Percentile 1m Bar Range: {p90_bar_range:.1f} pts")
    print(f"   Median Opening Range Width: {np.median(session_or_widths):.1f} pts | 90th Pct: {p90_or_width:.1f} pts")
    print(f"   Median Daily Session Range: {np.median(session_ranges):.1f} pts | 90th Pct: {p90_session_range:.1f} pts")

    # Dynamic SENSEX Regime Partitioning
    # 1. RANGE: Low ER (< 0.28) and moderate volatility
    range_mask = (df_metrics["er"] < 0.28) & (df_metrics["avg_range"] < p90_bar_range)

    # 2. TREND_UP: High ER (>= 0.45), net positive drift, above VWAP
    trend_up_mask = (df_metrics["er"] >= 0.45) & (df_metrics["net_change"] > 40.0) & (df_metrics["vwap_dist"] > 15.0)

    # 3. TREND_DOWN: High ER (>= 0.45), net negative drift, below VWAP
    trend_down_mask = (df_metrics["er"] >= 0.45) & (df_metrics["net_change"] < -40.0) & (df_metrics["vwap_dist"] < -15.0)

    # 4. VOLATILE_SHOCK: Extreme volatility bars (> 90th percentile) with low efficiency (erratic whipsaws)
    volatile_mask = (df_metrics["avg_range"] >= p90_bar_range) & (df_metrics["er"] < 0.35)

    calibrated_matrix = {
        "metadata": {
            "asset": "SENSEX",
            "historical_archive": parquet_path,
            "total_bars_analyzed": total_bars,
            "total_sessions": len(dates),
            "date_range": f"{df_raw['timestamp'].iloc[0]} to {df_raw['timestamp'].iloc[-1]}",
            "median_1m_bar_range_pts": round(median_bar_range, 1),
            "p90_opening_range_width_pts": round(p90_or_width, 1),
            "p90_daily_session_range_pts": round(p90_session_range, 1),
        },
        "RANGE": {
            "count": int(range_mask.sum()),
            "percentage": round(float(range_mask.mean() * 100), 1),
            "efficiency_ratio_max": 0.28,
            "action": "MICRO_SCALP_BOTH_WAYS",
            "optimal_target_pts": round(float(df_metrics[range_mask]["fwd_high"].quantile(0.60)), 1),
            "optimal_stop_loss_pts": round(float(df_metrics[range_mask]["fwd_low"].quantile(0.35)), 1),
            "optimal_rejection_wick_pts": round(max(15.0, median_bar_range * 0.7), 1),
            "optimal_profit_lock_trigger_pts": round(float(df_metrics[range_mask]["fwd_high"].quantile(0.35)), 1),
            "rules": "Fade rips at upper boundary; Buy dips at lower boundary/VWAP floor; Lock profits quickly."
        },
        "TRENDING_UP": {
            "count": int(trend_up_mask.sum()),
            "percentage": round(float(trend_up_mask.mean() * 100), 1),
            "efficiency_ratio_min": 0.45,
            "action": "PULLBACK_LONG_ONLY",
            "optimal_target_pts": round(float(df_metrics[trend_up_mask]["fwd_high"].quantile(0.75)), 1),
            "optimal_stop_loss_pts": round(float(df_metrics[trend_up_mask]["fwd_low"].quantile(0.40)), 1),
            "rules": "Buy pullbacks to VWAP; Strictly forbid shorting/fading; Trail stops."
        },
        "TRENDING_DOWN": {
            "count": int(trend_down_mask.sum()),
            "percentage": round(float(trend_down_mask.mean() * 100), 1),
            "efficiency_ratio_min": 0.45,
            "action": "BREAKDOWN_SHORT_ONLY",
            "optimal_target_pts": round(float(df_metrics[trend_down_mask]["fwd_low"].quantile(0.75)), 1),
            "optimal_stop_loss_pts": round(float(df_metrics[trend_down_mask]["fwd_high"].quantile(0.40)), 1),
            "rules": "Sell rallies to VWAP; Strictly forbid buying dips; Trail stops."
        },
        "VOLATILE_SHOCK": {
            "count": int(volatile_mask.sum()),
            "percentage": round(float(volatile_mask.mean() * 100), 1),
            "min_bar_range_pts": round(p90_bar_range, 1),
            "action": "STAND_ASIDE_100_PERCENT_CASH",
            "optimal_target_pts": 0.0,
            "optimal_stop_loss_pts": 0.0,
            "rules": "Enforce mandatory stand-aside; Vega shock & erratic wicks destroy capital."
        }
    }

    out_file = Path(out_matrix_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(calibrated_matrix, f, indent=2)

    print(f"\n=== SENSEX EMPIRICAL REGIME CALIBRATION COMPLETE ===")
    for reg in ["RANGE", "TRENDING_UP", "TRENDING_DOWN", "VOLATILE_SHOCK"]:
        d = calibrated_matrix[reg]
        print(f"{reg:15} | Pop: {d['percentage']:4.1f}% | Action: {d['action']:25} | Target: {d['optimal_target_pts']} pts | SL: {d['optimal_stop_loss_pts']} pts")

    print(f"\n✅ Frozen calibration matrix saved to: {out_matrix_path}")
    return calibrated_matrix


if __name__ == "__main__":
    calibrate_sensex(
        parquet_path="/Volumes/TradeBot/historical/sensex/sensex_1minute_2022_2026.parquet",
        out_matrix_path="artifacts/sensex_calibrated_regime_matrix.json"
    )
