"""Diagnostic Post-Mortem Evaluator for Strategy S5 (AREC-V1) on Arena 4 (2026).

PURPOSE:
- Regime diagnostic only. NOT a prospective rescue or edge recertification.
- Evaluates 2026 data using the exact frozen S5 specification:
  * Window: [13:30:00, 14:00:00) IST
  * Range: sess_range_so_far >= 0.0080 (80 bps)
  * Location: pos_in_sess_range >= 0.95 (Long) or <= 0.05 (Short)
  * Entry: Bar t+1 Open
  * Exit: Exact 15:15:00 IST Close
  * Max 1 trade per session
- Applies authoritative 2026 turnover statutory costs + 65-lot brokerage.
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
    table = pq.read_table(PARQUET_PATH, columns=["timestamp", "open", "high", "low", "close"])
    assert str(table.column("timestamp").type) == "timestamp[us, tz=Asia/Kolkata]", "Timezone error"

    df = table.to_pandas()
    # Isolate 2026 data strictly
    df = df[df["timestamp"].dt.year == 2026].sort_values("timestamp").reset_index(drop=True)
    if len(df) == 0:
        print("ERROR: No 2026 data found in canonical parquet.")
        return

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
                        "partition": "ARENA4_2026",
                        "year": 2026,
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
                        "partition": "ARENA4_2026",
                        "year": 2026,
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
    n_trades = len(tdf)
    print("\n=======================================================")
    print("=== ARENA 4 (2026) DIAGNOSTIC EXECUTION RESULT ===")
    print("=======================================================")
    print(f"2026 Trade Count (N):       {n_trades}")
    if n_trades == 0:
        print("Zero signals generated in 2026.")
        return

    long_df = tdf[tdf["side"] == "LONG"]
    short_df = tdf[tdf["side"] == "SHORT"]
    n_long = len(long_df)
    n_short = len(short_df)

    gross_mean_bps = tdf["gross_bps"].mean()
    gross_mean_pts = tdf["gross_pts"].mean()
    net_stat_bps = tdf["net_statutory_bps"].mean()
    net_stat_pts = tdf["net_statutory_pts"].mean()
    net_trad_bps = tdf["net_tradable_bps"].mean()
    net_trad_pts = tdf["net_tradable_pts"].mean()

    long_gross_bps = long_df["gross_bps"].mean() if n_long > 0 else 0.0
    short_gross_bps = short_df["gross_bps"].mean() if n_short > 0 else 0.0

    gross_wr = (tdf["gross_pts"] > 0).mean()
    net_stat_wr = (tdf["net_statutory_pts"] > 0).mean()

    print(f"Long Count / Short Count:   {n_long} Long / {n_short} Short")
    print(f"Gross Mean Expectancy:      {gross_mean_pts:+.2f} pts ({gross_mean_bps:+.2f} bps)")
    print(f"Net Statutory Expectancy:   {net_stat_pts:+.2f} pts ({net_stat_bps:+.2f} bps)")
    print(f"Net Tradable (@2pt spread): {net_trad_pts:+.2f} pts ({net_trad_bps:+.2f} bps)")
    print(f"Long Gross Mean:            {long_gross_bps:+.2f} bps")
    print(f"Short Gross Mean:           {short_gross_bps:+.2f} bps")
    print(f"Gross Win Rate:             {gross_wr:.1%}")
    print(f"Net Statutory Win Rate:     {net_stat_wr:.1%}")

    # Bootstrap 95% CI
    np.random.seed(42)
    boot_means = [np.random.choice(tdf["gross_bps"].values, size=n_trades, replace=True).mean() for _ in range(10000)]
    ci_lower = np.percentile(boot_means, 2.5)
    ci_upper = np.percentile(boot_means, 97.5)
    print(f"Bootstrap 95% CI (Gross):   [{ci_lower:+.2f}, {ci_upper:+.2f}] bps")

    # Diagnostic Classification
    if gross_mean_bps >= 8.00 and net_stat_bps > 0.0:
        diag_verdict = "REGIME_DEPENDENCE_HYPOTHESIS_STRENGTHENED"
    else:
        diag_verdict = "POST_2022_EDGE_DECAY_STRENGTHENED"

    print(f"\nDIAGNOSTIC_VERDICT:         {diag_verdict}")
    print("STATUS:                     S5_REMAINS_REJECTED (Arena 3 failure immutable)")
    print("=======================================================\n")

    # Save diagnostic trade schedule
    json_str = json.dumps(trades, indent=2, sort_keys=True)
    digest = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
    out_dir = "/Users/madhuram/.gemini/antigravity/brain/d516d3a0-4388-4841-8c76-34b1f34aee21/scratch"
    with open(f"{out_dir}/arena4_2026_diagnostic_schedule.json", "w") as f:
        f.write(json_str)
    print(f"Arena 4 Schedule SHA-256:   {digest}")


if __name__ == "__main__":
    main()
