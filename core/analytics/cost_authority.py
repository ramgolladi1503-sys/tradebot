"""Versioned Transaction Cost Authority for Indian Derivatives & Cash Markets.

Decouples statutory, regulatory, and broker friction schedules from raw strategy observations.
Supports versioned schedules with explicit verification status and effective dates.

Fails closed with COST_UNKNOWN when an authority is unverified or missing.
Never returns 0.0 for unverified cost models.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Literal

CostAuthorityStatus = Literal[
    "COST_AUTHORITY_VERIFIED",
    "UNVERIFIED",
    "COST_UNKNOWN",
]


@dataclass(frozen=True)
class CostBreakdown:
    stt_pts: float
    exchange_fee_pts: float
    stamp_duty_pts: float
    sebi_fee_pts: float
    gst_statutory_pts: float
    brokerage_pts: float
    gst_brokerage_pts: float
    total_friction_pts: float
    authority_id: str
    effective_date: str
    verification_status: CostAuthorityStatus


class CostAuthority:
    """Versioned cost calculation authority."""

    def __init__(
        self,
        authority_id: str,
        effective_date: str,
        verification_status: CostAuthorityStatus,
        stt_sell_rate: float,
        exchange_turnover_rate: float,
        stamp_duty_buy_rate: float,
        sebi_turnover_rate: float,
        gst_rate: float = 0.18,
        brokerage_pct: float = 0.0003,
        max_brokerage_per_order_rs: float = 20.0,
        source_citation: Optional[str] = None,
    ):
        self.authority_id = authority_id
        self.effective_date = effective_date
        self.verification_status = verification_status
        self.stt_sell_rate = stt_sell_rate
        self.exchange_turnover_rate = exchange_turnover_rate
        self.stamp_duty_buy_rate = stamp_duty_buy_rate
        self.sebi_turnover_rate = sebi_turnover_rate
        self.gst_rate = gst_rate
        self.brokerage_pct = brokerage_pct
        self.max_brokerage_per_order_rs = max_brokerage_per_order_rs
        self.source_citation = source_citation

    def compute_futures_cost(
        self,
        entry_px: float,
        exit_px: float,
        side: str,
        lot_size: int,
    ) -> Optional[CostBreakdown]:
        """Compute exact transaction friction in index points for 1 lot.

        Returns None if verification_status != 'COST_AUTHORITY_VERIFIED'.
        """
        if self.verification_status != "COST_AUTHORITY_VERIFIED":
            return None

        assert lot_size > 0, f"lot_size must be positive, got {lot_size}"
        side_upper = side.upper()
        assert side_upper in ("LONG", "SHORT"), f"Invalid side: {side}"

        turnover = entry_px + exit_px

        # STT on sell side only
        if side_upper == "LONG":
            stt_pts = exit_px * self.stt_sell_rate
            stamp_duty_pts = entry_px * self.stamp_duty_buy_rate
        else:
            stt_pts = entry_px * self.stt_sell_rate
            stamp_duty_pts = exit_px * self.stamp_duty_buy_rate

        exch_fee_pts = turnover * self.exchange_turnover_rate
        sebi_fee_pts = turnover * self.sebi_turnover_rate
        gst_statutory_pts = (exch_fee_pts + sebi_fee_pts) * self.gst_rate

        # Brokerage capped per leg in INR, converted to points
        entry_val_rs = entry_px * lot_size
        brok_entry_rs = min(entry_val_rs * self.brokerage_pct, self.max_brokerage_per_order_rs)
        exit_val_rs = exit_px * lot_size
        brok_exit_rs = min(exit_val_rs * self.brokerage_pct, self.max_brokerage_per_order_rs)

        total_brok_rs = brok_entry_rs + brok_exit_rs
        brokerage_pts = total_brok_rs / lot_size
        gst_brokerage_pts = (total_brok_rs * self.gst_rate) / lot_size

        total_friction_pts = (
            stt_pts
            + stamp_duty_pts
            + exch_fee_pts
            + sebi_fee_pts
            + gst_statutory_pts
            + brokerage_pts
            + gst_brokerage_pts
        )

        return CostBreakdown(
            stt_pts=round(stt_pts, 4),
            exchange_fee_pts=round(exch_fee_pts, 4),
            stamp_duty_pts=round(stamp_duty_pts, 4),
            sebi_fee_pts=round(sebi_fee_pts, 4),
            gst_statutory_pts=round(gst_statutory_pts, 4),
            brokerage_pts=round(brokerage_pts, 4),
            gst_brokerage_pts=round(gst_brokerage_pts, 4),
            total_friction_pts=round(total_friction_pts, 4),
            authority_id=self.authority_id,
            effective_date=self.effective_date,
            verification_status=self.verification_status,
        )


# Registry of versioned cost schedules
# Declared UNVERIFIED until official NSE/SEBI circular circular-hashes are verified
COST_AUTHORITY_REGISTRY: Dict[str, CostAuthority] = {
    "NSE_FUTURES_2026_UNVERIFIED_PROVISIONAL": CostAuthority(
        authority_id="NSE_FUTURES_2026_UNVERIFIED_PROVISIONAL",
        effective_date="2026-04-01",
        verification_status="UNVERIFIED",
        stt_sell_rate=0.0005,
        exchange_turnover_rate=0.0000183,
        stamp_duty_buy_rate=0.00002,
        sebi_turnover_rate=0.0000010,
        gst_rate=0.18,
        brokerage_pct=0.0003,
        max_brokerage_per_order_rs=20.0,
        source_citation="Provisional estimate based on illustrative research reports; pending official circular hash verification",
    ),
}


def get_cost_authority(authority_id: str) -> Optional[CostAuthority]:
    """Retrieve cost authority by ID or None if unknown (fail-closed)."""
    return COST_AUTHORITY_REGISTRY.get(authority_id)
