"""Authoritative Generator and Evaluator for Strategy S5 (AREC-V1).

Contract Specification:
- Observation Window: 13:30:00 <= timestamp.time() < 14:00:00 Asia/Kolkata (14:00:00 excluded).
- Invariant Condition: sess_range_so_far >= 0.0080 (80 bps).
- Directional Boundary: pos_in_sess_range >= 0.95 (Long) or <= 0.05 (Short).
- Execution: Causal next-bar Open (bar t+1 Open).
- Terminal Exit: Same-day timestamp.time() == 15:15:00 Asia/Kolkata Close.
- Max Frequency: At most 1 trade per session.
"""

from __future__ import annotations
import sys
import os
import datetime
import json
import hashlib
import pyarrow.parquet as pq
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from core.analytics.nifty_futures_cost_engine import compute_nifty_futures_costs

PARQUET_PATH = "/Volumes/TradeBotData/strategy_research_canonical/acquisitions/nifty50/20260908_master_1m_2009_2026_v3/canonical/NIFTY50_1m_2009_2026_v3_research_ready.parquet"


def generate_s5_schedule(max_year: int = 2022) -> list[dict]:
    table = pq.read_table(PARQUET_PATH, columns=["timestamp", "open", "high", "low", "close"])
    assert str(table.column("timestamp").type) == "timestamp[us, tz=Asia/Kolkata]", (
        "Dataset timezone must be timestamp[us, tz=Asia/Kolkata]"
    )

    df = table.to_pandas()
    df = df[df["timestamp"].dt.year <= max_year].sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date
    df["time"] = df["timestamp"].dt.time
    df["year"] = df["timestamp"].dt.year

    days = {d: g.reset_index(drop=True) for d, g in df.groupby("date")}
    target_exit_time = datetime.time(15, 15)

    trades = []
    for d in sorted(days.keys()):
        g = days[d]
        exit_matches = g[g["time"] == target_exit_time]
        if exit_matches.empty:
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
                    net_tradable_pts = round(gross_pts - costs.total_friction_pts, 2)

                    trades.append({
                        "partition": "DEV" if entry_bar["year"] <= 2018 else "ARENA2",
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
                        "exch_fee_pts": costs.exch_fee_pts,
                        "stamp_duty_pts": costs.stamp_duty_pts,
                        "sebi_fee_pts": costs.sebi_fee_pts,
                        "gst_statutory_pts": costs.gst_statutory_pts,
                        "statutory_total_pts": costs.statutory_total_pts,
                        "brokerage_pts": costs.brokerage_pts,
                        "gst_brokerage_pts": costs.gst_brokerage_pts,
                        "net_statutory_pts": net_stat_pts,
                        "net_tradable_pts": net_tradable_pts,
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
                    net_tradable_pts = round(gross_pts - costs.total_friction_pts, 2)

                    trades.append({
                        "partition": "DEV" if entry_bar["year"] <= 2018 else "ARENA2",
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
                        "exch_fee_pts": costs.exch_fee_pts,
                        "stamp_duty_pts": costs.stamp_duty_pts,
                        "sebi_fee_pts": costs.sebi_fee_pts,
                        "gst_statutory_pts": costs.gst_statutory_pts,
                        "statutory_total_pts": costs.statutory_total_pts,
                        "brokerage_pts": costs.brokerage_pts,
                        "gst_brokerage_pts": costs.gst_brokerage_pts,
                        "net_statutory_pts": net_stat_pts,
                        "net_tradable_pts": net_tradable_pts,
                    })
                    break

    return trades


if __name__ == "__main__":
    trades = generate_s5_schedule(2022)
    print(f"Generated {len(trades)} trades across DEV and ARENA 2.")
    json_str = json.dumps(trades, indent=2, sort_keys=True)
    digest = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
    print(f"Schedule SHA-256 Digest: {digest}")
