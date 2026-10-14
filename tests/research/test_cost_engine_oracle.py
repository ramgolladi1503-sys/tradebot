"""Independent Golden Oracle Test for 2026 NIFTY Futures Cost Engine.

Completely independent implementation of the NSE/SEBI/Brokerage statutory rules
without importing or sharing any logic from nifty_futures_cost_engine.py.

Tests 5 deterministic benchmark trades across multiple price regimes:
1. Low Price Regime: 5,000.00
2. Moderate Price Regime: 10,000.00
3. Historical Median: 15,000.00
4. High Regime: 22,000.00
5. ATH Regime: 25,000.00
"""

from __future__ import annotations
import pytest
from core.analytics.nifty_futures_cost_engine import compute_nifty_futures_costs


def manual_golden_oracle(entry_px: float, exit_px: float, side: str, lot_size: int = 65):
    """Hand-calculated mathematical oracle."""
    turnover = entry_px + exit_px
    
    # STT: 0.05% on sell side only
    if side == "LONG":
        stt = exit_px * 0.0005
        stamp = entry_px * 0.00002
    else:
        stt = entry_px * 0.0005
        stamp = exit_px * 0.00002
        
    # Exchange fee: Rs 183 per crore per side = 0.0000183 * turnover
    exch = turnover * 0.0000183
    
    # SEBI fee: Rs 10 per crore = 0.0000010 * turnover
    sebi = turnover * 0.0000010
    
    # GST on (exch + sebi): 18%
    gst_stat = (exch + sebi) * 0.18
    
    stat_total = stt + stamp + exch + sebi + gst_stat
    
    # Brokerage: min(0.03%, Rs 20) per order
    # Entry value
    val_entry = entry_px * lot_size
    brok_entry = min(val_entry * 0.0003, 20.0)
    
    val_exit = exit_px * lot_size
    brok_exit = min(val_exit * 0.0003, 20.0)
    
    total_brok_rs = brok_entry + brok_exit
    brok_pts = total_brok_rs / lot_size
    gst_brok_pts = (total_brok_rs * 0.18) / lot_size
    
    total_friction_zero_spread = stat_total + brok_pts + gst_brok_pts
    
    return {
        "stt": round(stt, 4),
        "exch": round(exch, 4),
        "stamp": round(stamp, 4),
        "sebi": round(sebi, 4),
        "gst_stat": round(gst_stat, 4),
        "stat_total": round(stat_total, 4),
        "brok_pts": round(brok_pts, 4),
        "gst_brok_pts": round(gst_brok_pts, 4),
        "total_friction": round(total_friction_zero_spread, 4),
    }


@pytest.mark.parametrize(
    "entry_px,exit_px,side",
    [
        (5000.0, 5020.0, "LONG"),
        (10000.0, 9950.0, "SHORT"),
        (15000.0, 15050.0, "LONG"),
        (22000.0, 21900.0, "SHORT"),
        (25000.0, 25100.0, "LONG"),
    ],
)
def test_golden_cost_engine_oracle(entry_px: float, exit_px: float, side: str):
    oracle = manual_golden_oracle(entry_px, exit_px, side, lot_size=65)
    engine = compute_nifty_futures_costs(entry_px, exit_px, side, lot_size=65, spread_slippage_pts=0.0)
    
    assert engine.stt_pts == oracle["stt"]
    assert engine.exch_fee_pts == oracle["exch"]
    assert engine.stamp_duty_pts == oracle["stamp"]
    assert engine.sebi_fee_pts == oracle["sebi"]
    assert engine.gst_statutory_pts == oracle["gst_stat"]
    assert engine.statutory_total_pts == oracle["stat_total"]
    assert engine.brokerage_pts == oracle["brok_pts"]
    assert engine.gst_brokerage_pts == oracle["gst_brok_pts"]
    assert engine.total_friction_pts == oracle["total_friction"]
