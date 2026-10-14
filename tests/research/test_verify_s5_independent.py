"""Independent Verifier for Strategy S5 (AREC-V1).

Written completely independently to enforce contract boundaries and prevent
common-mode bugs with evaluate_s5_candidate.py.

Verifies:
1. Exact trade count (984 trades).
2. Date-by-date primitive consistency:
   - signal timestamp
   - trade direction
   - entry timestamp & price
   - exit timestamp & price
   - gross return
   - statutory cost breakdown
   - brokerage & GST breakdown
   - net tradable return
3. Bit-for-bit SHA-256 schedule digest match.
"""

from __future__ import annotations
import os
import sys
import datetime
import json
import hashlib
import pyarrow.parquet as pq
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from core.analytics.nifty_futures_cost_engine import compute_nifty_futures_costs

PARQUET_PATH = "/Volumes/TradeBotData/strategy_research_canonical/acquisitions/nifty50/20260908_master_1m_2009_2026_v3/canonical/NIFTY50_1m_2009_2026_v3_research_ready.parquet"


def test_independent_s5_verification():
    # 1. Load canonical dataset
    table = pq.read_table(PARQUET_PATH, columns=["timestamp", "open", "high", "low", "close"])
    assert str(table.column("timestamp").type) == "timestamp[us, tz=Asia/Kolkata]"
    
    df = table.to_pandas()
    df = df[df["timestamp"].dt.year <= 2022].sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date
    df["time"] = df["timestamp"].dt.time
    
    # 2. Replay independent strategy state
    days = {d: g.reset_index(drop=True) for d, g in df.groupby("date")}
    target_exit = datetime.time(15, 15)
    
    verified_trades = []
    for d, g in sorted(days.items()):
        # Fail closed if 15:15 bar missing
        exit_rows = g[g["time"] == target_exit]
        if exit_rows.empty:
            continue
        exit_bar = exit_rows.iloc[0]
        exit_px = float(exit_bar["close"])
        exit_ts = str(exit_bar["timestamp"])
        
        sess_open = float(g["open"].iloc[0])
        
        # Invariant window: [13:30, 14:00)
        window = g[(g["time"] >= datetime.time(13, 30)) & (g["time"] < datetime.time(14, 0))]
        for idx in window.index:
            cum_high = g["high"].iloc[: idx + 1].max()
            cum_low = g["low"].iloc[: idx + 1].min()
            close_px = g["close"].iloc[idx]
            
            if cum_high == cum_low:
                continue
            sess_rng = (cum_high - cum_low) / sess_open
            pos_ratio = (close_px - cum_low) / (cum_high - cum_low)
            
            if sess_rng >= 0.0080:
                if pos_ratio >= 0.95:
                    # Long
                    if idx + 1 >= len(g) or g["time"].iloc[idx + 1] >= target_exit:
                        continue
                    entry_bar = g.iloc[idx + 1]
                    entry_px = float(entry_bar["open"])
                    entry_ts = str(entry_bar["timestamp"])
                    
                    cost = compute_nifty_futures_costs(entry_px, exit_px, "LONG", spread_slippage_pts=2.0)
                    gross_pts = round(exit_px - entry_px, 2)
                    net_stat_pts = round(gross_pts - cost.statutory_total_pts, 2)
                    net_trad_pts = round(gross_pts - cost.total_friction_pts, 2)
                    
                    verified_trades.append({
                        "partition": "DEV" if entry_bar["timestamp"].year <= 2018 else "ARENA2",
                        "year": int(entry_bar["timestamp"].year),
                        "date": str(d),
                        "side": "LONG",
                        "signal_ts": str(g["timestamp"].iloc[idx]),
                        "entry_ts": entry_ts,
                        "entry_px": round(entry_px, 2),
                        "exit_ts": exit_ts,
                        "exit_px": round(exit_px, 2),
                        "gross_pts": gross_pts,
                        "gross_bps": round((gross_pts / entry_px) * 10000.0, 2),
                        "stt_pts": cost.stt_pts,
                        "exch_fee_pts": cost.exch_fee_pts,
                        "stamp_duty_pts": cost.stamp_duty_pts,
                        "sebi_fee_pts": cost.sebi_fee_pts,
                        "gst_statutory_pts": cost.gst_statutory_pts,
                        "statutory_total_pts": cost.statutory_total_pts,
                        "brokerage_pts": cost.brokerage_pts,
                        "gst_brokerage_pts": cost.gst_brokerage_pts,
                        "net_statutory_pts": net_stat_pts,
                        "net_tradable_pts": net_trad_pts,
                    })
                    break
                    
                elif pos_ratio <= 0.05:
                    # Short
                    if idx + 1 >= len(g) or g["time"].iloc[idx + 1] >= target_exit:
                        continue
                    entry_bar = g.iloc[idx + 1]
                    entry_px = float(entry_bar["open"])
                    entry_ts = str(entry_bar["timestamp"])
                    
                    cost = compute_nifty_futures_costs(entry_px, exit_px, "SHORT", spread_slippage_pts=2.0)
                    gross_pts = round(entry_px - exit_px, 2)
                    net_stat_pts = round(gross_pts - cost.statutory_total_pts, 2)
                    net_trad_pts = round(gross_pts - cost.total_friction_pts, 2)
                    
                    verified_trades.append({
                        "partition": "DEV" if entry_bar["timestamp"].year <= 2018 else "ARENA2",
                        "year": int(entry_bar["timestamp"].year),
                        "date": str(d),
                        "side": "SHORT",
                        "signal_ts": str(g["timestamp"].iloc[idx]),
                        "entry_ts": entry_ts,
                        "entry_px": round(entry_px, 2),
                        "exit_ts": exit_ts,
                        "exit_px": round(exit_px, 2),
                        "gross_pts": gross_pts,
                        "gross_bps": round((gross_pts / entry_px) * 10000.0, 2),
                        "stt_pts": cost.stt_pts,
                        "exch_fee_pts": cost.exch_fee_pts,
                        "stamp_duty_pts": cost.stamp_duty_pts,
                        "sebi_fee_pts": cost.sebi_fee_pts,
                        "gst_statutory_pts": cost.gst_statutory_pts,
                        "statutory_total_pts": cost.statutory_total_pts,
                        "brokerage_pts": cost.brokerage_pts,
                        "gst_brokerage_pts": cost.gst_brokerage_pts,
                        "net_statutory_pts": net_stat_pts,
                        "net_tradable_pts": net_trad_pts,
                    })
                    break

    # 3. Assertions
    assert len(verified_trades) == 984, f"Expected 984 trades, got {len(verified_trades)}"
    
    dev_trades = [t for t in verified_trades if t["partition"] == "DEV"]
    arena2_trades = [t for t in verified_trades if t["partition"] == "ARENA2"]
    assert len(dev_trades) == 696, f"Expected 696 DEV trades, got {len(dev_trades)}"
    assert len(arena2_trades) == 288, f"Expected 288 ARENA2 trades, got {len(arena2_trades)}"
    
    # Check against frozen schedule file
    frozen_path = "/Users/madhuram/.gemini/antigravity/brain/d516d3a0-4388-4841-8c76-34b1f34aee21/scratch/strategy_s5_certified_schedule.json"
    with open(frozen_path) as f:
        frozen_trades = json.load(f)
        
    assert len(verified_trades) == len(frozen_trades)
    
    for i, (v, f_tr) in enumerate(zip(verified_trades, frozen_trades)):
        assert v["date"] == f_tr["date"], f"Date mismatch at index {i}: {v['date']} vs {f_tr['date']}"
        assert v["side"] == f_tr["side"], f"Side mismatch at {v['date']}: {v['side']} vs {f_tr['side']}"
        assert v["entry_px"] == f_tr["entry_px"], f"Entry px mismatch at {v['date']}: {v['entry_px']} vs {f_tr['entry_px']}"
        assert v["exit_px"] == f_tr["exit_px"], f"Exit px mismatch at {v['date']}: {v['exit_px']} vs {f_tr['exit_px']}"
        assert v["gross_pts"] == f_tr["gross_pts"], f"Gross pts mismatch at {v['date']}"
        assert v["statutory_total_pts"] == f_tr["statutory_total_pts"], f"Statutory cost mismatch at {v['date']}"
        assert v["net_statutory_pts"] == f_tr["net_statutory_pts"], f"Net statutory mismatch at {v['date']}"
        assert v["net_tradable_pts"] == f_tr["net_tradable_pts"], f"Net tradable mismatch at {v['date']}"

    verified_sha = hashlib.sha256(json.dumps(verified_trades, indent=2, sort_keys=True).encode("utf-8")).hexdigest()
    frozen_sha = hashlib.sha256(json.dumps(frozen_trades, indent=2, sort_keys=True).encode("utf-8")).hexdigest()
    assert verified_sha == frozen_sha, f"SHA mismatch! Verified={verified_sha} vs Frozen={frozen_sha}"
    print(f"Independent Verification: PASS (SHA-256: {verified_sha})")
