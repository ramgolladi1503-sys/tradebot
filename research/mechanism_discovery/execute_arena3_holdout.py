"""Single-Shot OOS Holdout Evaluator for Strategy S5 (AREC-V1) on Arena 3 (2023-2025).

RULES:
1. Strictly evaluates 2023-01-01 to 2025-12-31 only. 2026 data is FORBIDDEN.
2. Applies frozen S5 specification:
   - Window: [13:30:00, 14:00:00) IST
   - Invariant: sess_range_so_far >= 0.0080 (80 bps)
   - Extremity: pos_in_sess_range >= 0.95 (Long) or <= 0.05 (Short)
   - Entry: Causal next-bar Open
   - Exit: Exact 15:15:00 IST bar Close
   - Max 1 trade per session
3. Computes exact 2026 statutory costs + lot-65 brokerage + 2.0 pt spread scenario.
4. Performs 10,000-iteration percentile bootstrap with seed=42.
5. Programmatically applies the frozen Arena 3 Acceptance Matrix to emit FINAL_VERDICT.
"""

from __future__ import annotations
import sys
import os
import datetime
import json
import hashlib
import pyarrow.parquet as pq
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from core.analytics.nifty_futures_cost_engine import compute_nifty_futures_costs

PARQUET_PATH = "/Volumes/TradeBotData/strategy_research_canonical/acquisitions/nifty50/20260908_master_1m_2009_2026_v3/canonical/NIFTY50_1m_2009_2026_v3_research_ready.parquet"


def main():
    # 1. Load canonical dataset and strictly isolate 2023-2025
    table = pq.read_table(PARQUET_PATH, columns=["timestamp", "open", "high", "low", "close"])
    assert str(table.column("timestamp").type) == "timestamp[us, tz=Asia/Kolkata]", "Timezone error"

    df = table.to_pandas()
    # FORBIDDEN: Any access to 2026
    df = df[(df["timestamp"].dt.year >= 2023) & (df["timestamp"].dt.year <= 2025)].sort_values("timestamp").reset_index(drop=True)
    assert df["timestamp"].dt.year.max() == 2025, "Data leakage: year > 2025 detected!"
    assert df["timestamp"].dt.year.min() == 2023, "Data leakage: year < 2023 detected!"

    df["date"] = df["timestamp"].dt.date
    df["time"] = df["timestamp"].dt.time
    df["year"] = df["timestamp"].dt.year

    days = {d: g.reset_index(drop=True) for d, g in df.groupby("date")}
    target_exit_time = datetime.time(15, 15)

    trades = []
    skipped_days = []

    for d in sorted(days.keys()):
        g = days[d]
        exit_matches = g[g["time"] == target_exit_time]
        if exit_matches.empty:
            skipped_days.append(str(d))
            continue
        exit_bar = exit_matches.iloc[0]
        exit_px = float(exit_bar["close"])
        exit_ts = str(exit_bar["timestamp"])
        sess_open = float(g["open"].iloc[0])

        w_mask = (g["time"] >= datetime.time(13, 30)) & (g["time"] < datetime.time(14, 0))
        for idx in g[w_mask].index:
            h = g["high"].iloc[: idx + 1].max()
            l = g["low"].iloc[: idx + 1].min()
            c = g["close"].iloc[idx]

            if h == l:
                continue
            sess_range = (h - l) / sess_open
            pos = (c - l) / (h - l)

            if sess_range >= 0.0080:
                if pos >= 0.95:
                    if idx + 1 >= len(g) or g["time"].iloc[idx + 1] >= target_exit_time:
                        continue
                    entry_bar = g.iloc[idx + 1]
                    entry_px = float(entry_bar["open"])
                    entry_ts = str(entry_bar["timestamp"])

                    costs = compute_nifty_futures_costs(entry_px, exit_px, "LONG", spread_slippage_pts=2.0)
                    gross_pts = round(exit_px - entry_px, 2)
                    net_stat_pts = round(gross_pts - costs.statutory_total_pts, 2)
                    net_trad_pts = round(gross_pts - costs.total_friction_pts, 2)

                    trades.append({
                        "partition": "ARENA3",
                        "year": int(entry_bar["year"]),
                        "date": str(d),
                        "side": "LONG",
                        "signal_ts": str(g["timestamp"].iloc[idx]),
                        "entry_ts": entry_ts,
                        "entry_px": round(entry_px, 2),
                        "exit_ts": exit_ts,
                        "exit_px": round(exit_px, 2),
                        "gross_pts": gross_pts,
                        "gross_bps": round((gross_pts / entry_px) * 10000.0, 2),
                        "stt_pts": costs.stt_pts,
                        "statutory_total_pts": costs.statutory_total_pts,
                        "net_statutory_pts": net_stat_pts,
                        "net_statutory_bps": round((net_stat_pts / entry_px) * 10000.0, 2),
                        "net_tradable_pts": net_trad_pts,
                        "net_tradable_bps": round((net_trad_pts / entry_px) * 10000.0, 2),
                    })
                    break

                elif pos <= 0.05:
                    if idx + 1 >= len(g) or g["time"].iloc[idx + 1] >= target_exit_time:
                        continue
                    entry_bar = g.iloc[idx + 1]
                    entry_px = float(entry_bar["open"])
                    entry_ts = str(entry_bar["timestamp"])

                    costs = compute_nifty_futures_costs(entry_px, exit_px, "SHORT", spread_slippage_pts=2.0)
                    gross_pts = round(entry_px - exit_px, 2)
                    net_stat_pts = round(gross_pts - costs.statutory_total_pts, 2)
                    net_trad_pts = round(gross_pts - costs.total_friction_pts, 2)

                    trades.append({
                        "partition": "ARENA3",
                        "year": int(entry_bar["year"]),
                        "date": str(d),
                        "side": "SHORT",
                        "signal_ts": str(g["timestamp"].iloc[idx]),
                        "entry_ts": entry_ts,
                        "entry_px": round(entry_px, 2),
                        "exit_ts": exit_ts,
                        "exit_px": round(exit_px, 2),
                        "gross_pts": gross_pts,
                        "gross_bps": round((gross_pts / entry_px) * 10000.0, 2),
                        "stt_pts": costs.stt_pts,
                        "statutory_total_pts": costs.statutory_total_pts,
                        "net_statutory_pts": net_stat_pts,
                        "net_statutory_bps": round((net_stat_pts / entry_px) * 10000.0, 2),
                        "net_tradable_pts": net_trad_pts,
                        "net_tradable_bps": round((net_trad_pts / entry_px) * 10000.0, 2),
                    })
                    break

    tdf = pd.DataFrame(trades)
    
    # Check sample sufficiency
    n_trades = len(tdf)
    if n_trades == 0:
        print("ERROR: Zero trades produced in Arena 3.")
        return

    # Basic trade counts
    long_df = tdf[tdf["side"] == "LONG"]
    short_df = tdf[tdf["side"] == "SHORT"]
    n_long = len(long_df)
    n_short = len(short_df)

    # Performance metrics
    gross_mean_bps = tdf["gross_bps"].mean()
    net_stat_mean_bps = tdf["net_statutory_bps"].mean()
    net_2pt_scenario_mean_bps = tdf["net_tradable_bps"].mean()

    # Annual Breakdown
    annual_gross_bps = {}
    for y in [2023, 2024, 2025]:
        ydf = tdf[tdf["year"] == y]
        annual_gross_bps[y] = ydf["gross_bps"].mean() if len(ydf) > 0 else -999.0

    worst_year_bps = min(annual_gross_bps.values())
    positive_years_count = sum(1 for v in annual_gross_bps.values() if v > 0)

    # Directional Breakdown
    long_gross_bps = long_df["gross_bps"].mean() if n_long > 0 else -999.0
    short_gross_bps = short_df["gross_bps"].mean() if n_short > 0 else -999.0
    weaker_side_bps = min(long_gross_bps, short_gross_bps)

    # Bootstrap 95% CI
    BOOTSTRAP_SEED = 42
    BOOTSTRAP_REPS = 10000
    np.random.seed(BOOTSTRAP_SEED)
    gross_bps_array = tdf["gross_bps"].values
    boot_means = [np.random.choice(gross_bps_array, size=n_trades, replace=True).mean() for _ in range(BOOTSTRAP_REPS)]
    ci95_lower = np.percentile(boot_means, 2.5)
    ci95_upper = np.percentile(boot_means, 97.5)

    # Gate Evaluations from Frozen Matrix:
    # Sample Sufficiency Gate
    if n_trades >= 180:
        sample_suff = "ADEQUATE_SAMPLE"
    elif n_trades >= 150:
        sample_suff = "MARGINAL_SAMPLE"
    else:
        sample_suff = "INSUFFICIENT_SAMPLE"

    # Gate G1: Gross Mean Expectancy
    if gross_mean_bps >= 8.00:
        g1_status = "FULL"
    elif gross_mean_bps >= 5.00:
        g1_status = "WEAK"
    else:
        g1_status = "FAIL"

    # Gate G2: Net Statutory Expectancy
    if net_stat_mean_bps >= 2.00:
        g2_status = "FULL"
    elif net_stat_mean_bps >= 0.00:
        g2_status = "WEAK"
    else:
        g2_status = "FAIL"

    # Gate G3: Annual Stability & Worst Year
    if positive_years_count == 3 and worst_year_bps >= -3.00:
        g3_status = "FULL"
    elif positive_years_count == 2 and worst_year_bps >= -8.00:
        g3_status = "WEAK"
    else:
        g3_status = "FAIL"

    # Gate G4: Bootstrap 95% CI Lower Bound
    if ci95_lower > 0.00:
        g4_status = "FULL"
    elif ci95_lower >= -2.00:
        g4_status = "WEAK"
    else:
        g4_status = "FAIL"

    # Gate G5: Directional Balance
    if long_gross_bps > 0.00 and short_gross_bps > 0.00:
        g5_status = "FULL"
    elif weaker_side_bps >= -5.00:
        g5_status = "WEAK"
    else:
        g5_status = "FAIL"

    # Programmatic Aggregation Engine
    all_gates = [g1_status, g2_status, g3_status, g4_status, g5_status]

    if sample_suff == "INSUFFICIENT_SAMPLE":
        final_verdict = "OOS_INCONCLUSIVE_INSUFFICIENT_SAMPLE"
    elif "FAIL" in all_gates:
        final_verdict = "CLEAN_OOS_REJECTED"
    elif sample_suff == "ADEQUATE_SAMPLE" and all(status == "FULL" for status in all_gates):
        final_verdict = "CLEAN_OOS_FULL_PASS"
    else:
        final_verdict = "CLEAN_OOS_CONDITIONAL_WEAK_PASS"

    # Save frozen schedule of Arena 3
    arena3_schedule_json = json.dumps(trades, indent=2, sort_keys=True)
    arena3_schedule_sha = hashlib.sha256(arena3_schedule_json.encode("utf-8")).hexdigest()
    
    out_dir = "/Users/madhuram/.gemini/antigravity/brain/d516d3a0-4388-4841-8c76-34b1f34aee21/scratch"
    with open(f"{out_dir}/arena3_holdout_schedule.json", "w") as f:
        f.write(arena3_schedule_json)

    # Print exact required output
    print("\n=======================================================")
    print("=== ARENA 3 ONE-SHOT HOLDOUT VERIFICATION RESULT ===")
    print("=======================================================")
    print(f"N:                         {n_trades}")
    print(f"LONG_N:                    {n_long}")
    print(f"SHORT_N:                   {n_short}")
    print()
    print(f"GROSS_MEAN_BPS:            {gross_mean_bps:+.2f}")
    print(f"NET_STATUTORY_MEAN_BPS:    {net_stat_mean_bps:+.2f}")
    print(f"NET_2PT_SCENARIO_MEAN_BPS: {net_2pt_scenario_mean_bps:+.2f}")
    print()
    print(f"2023_GROSS_BPS:            {annual_gross_bps[2023]:+.2f} (N={len(tdf[tdf['year']==2023])})")
    print(f"2024_GROSS_BPS:            {annual_gross_bps[2024]:+.2f} (N={len(tdf[tdf['year']==2024])})")
    print(f"2025_GROSS_BPS:            {annual_gross_bps[2025]:+.2f} (N={len(tdf[tdf['year']==2025])})")
    print()
    print(f"LONG_GROSS_BPS:            {long_gross_bps:+.2f}")
    print(f"SHORT_GROSS_BPS:           {short_gross_bps:+.2f}")
    print()
    print(f"BOOTSTRAP_SEED:            {BOOTSTRAP_SEED}")
    print(f"BOOTSTRAP_REPS:            {BOOTSTRAP_REPS}")
    print(f"CI95_LOWER:                {ci95_lower:+.2f}")
    print(f"CI95_UPPER:                {ci95_upper:+.2f}")
    print()
    print(f"G1:                        {g1_status}")
    print(f"G2:                        {g2_status}")
    print(f"G3:                        {g3_status}")
    print(f"G4:                        {g4_status}")
    print(f"G5:                        {g5_status}")
    print(f"SAMPLE_SUFFICIENCY:        {sample_suff}")
    print()
    print(f"FINAL_VERDICT:             {final_verdict}")
    print(f"ARENA3_SCHEDULE_SHA256:    {arena3_schedule_sha}")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
