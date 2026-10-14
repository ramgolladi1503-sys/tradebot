"""Authoritative 2026 Transaction Cost Engine for NIFTY Futures.

Implements the official NSE and SEBI statutory schedules effective March/April 2026:
1. STT: 0.05% on the sell side (Futures taxable value = traded price).
2. NSE Transaction Charges: Rs 182.99/cr + Rs 0.01/cr IPFT = Rs 183/cr per side (0.00183% of turnover).
3. Stamp Duty: 0.002% on the buy side.
4. SEBI Turnover Charges: Rs 10/cr (0.0001% of turnover).
5. GST: 18% applied to (Exchange fee + SEBI fee + Brokerage).
6. Brokerage: Standard discount broker tariff: min(0.03% of contract value, Rs 20) per executed order.
   Converted to index points using current NIFTY market lot size (65).
"""

from __future__ import annotations
from dataclasses import dataclass

NIFTY_LOT_SIZE = 65


@dataclass(frozen=True)
class TradeCostBreakdown:
    stt_pts: float
    exch_fee_pts: float
    stamp_duty_pts: float
    sebi_fee_pts: float
    gst_statutory_pts: float
    statutory_total_pts: float
    brokerage_pts: float
    gst_brokerage_pts: float
    total_friction_pts: float


def compute_nifty_futures_costs(
    entry_px: float,
    exit_px: float,
    side: str,
    lot_size: int = NIFTY_LOT_SIZE,
    spread_slippage_pts: float = 0.0,
) -> TradeCostBreakdown:
    """Compute exact per-trade index point deductions for 1 lot of NIFTY Futures."""
    side_upper = side.upper()
    assert side_upper in ("LONG", "SHORT"), f"Invalid side: {side}"

    # 1. Turnover in index points
    turnover = entry_px + exit_px

    # 2. STT: 0.05% on Sell side only
    if side_upper == "LONG":
        # Buy entry, Sell exit -> STT on exit
        stt_pts = exit_px * 0.0005
        stamp_duty_pts = entry_px * 0.00002
    else:
        # Sell entry, Buy exit -> STT on entry
        stt_pts = entry_px * 0.0005
        stamp_duty_pts = exit_px * 0.00002

    # 3. Exchange transaction fee: Rs 183 per crore per side = 0.0000183 * turnover
    exch_fee_pts = turnover * 0.0000183

    # 4. SEBI fee: Rs 10 per crore = 0.0000010 * turnover
    sebi_fee_pts = turnover * 0.0000010

    # 5. GST on Statutory Dues (Exchange + SEBI)
    gst_statutory_pts = (exch_fee_pts + sebi_fee_pts) * 0.18

    # Statutory total
    statutory_total_pts = (
        stt_pts + stamp_duty_pts + exch_fee_pts + sebi_fee_pts + gst_statutory_pts
    )

    # 6. Brokerage: min(0.03%, Rs 20) per order
    # Entry contract value in Rupees = entry_px * lot_size
    # 0.03% of entry value:
    entry_val_rs = entry_px * lot_size
    brok_entry_rs = min(entry_val_rs * 0.0003, 20.0)

    exit_val_rs = exit_px * lot_size
    brok_exit_rs = min(exit_val_rs * 0.0003, 20.0)

    total_brok_rs = brok_entry_rs + brok_exit_rs
    brokerage_pts = total_brok_rs / lot_size

    # GST on Brokerage: 18%
    gst_brok_rs = total_brok_rs * 0.18
    gst_brokerage_pts = gst_brok_rs / lot_size

    total_friction_pts = (
        statutory_total_pts + brokerage_pts + gst_brokerage_pts + spread_slippage_pts
    )

    return TradeCostBreakdown(
        stt_pts=round(stt_pts, 4),
        exch_fee_pts=round(exch_fee_pts, 4),
        stamp_duty_pts=round(stamp_duty_pts, 4),
        sebi_fee_pts=round(sebi_fee_pts, 4),
        gst_statutory_pts=round(gst_statutory_pts, 4),
        statutory_total_pts=round(statutory_total_pts, 4),
        brokerage_pts=round(brokerage_pts, 4),
        gst_brokerage_pts=round(gst_brokerage_pts, 4),
        total_friction_pts=round(total_friction_pts, 4),
    )
