"""Sentinel Dynamic Sizing Engine.

Implements Gate 1 (Capital Discretization & Integer Lot Math):
- Invariant 1.1: Integer lot sizing must be strictly computed as floor(allocated_capital / lot_notional).
- Invariant 1.2 (Floor-or-Reject): If computed_lots < 1, sizing MUST return lots = 0 and
  tier "REJECT_INSUFFICIENT_MARGIN" (or "ZERO_SUPPRESS"). Sizing must NEVER round up to 1.
- Invariant 1.3: Support exchange lot sizes:
  NIFTY: 65 (or SEBI standard), BANKNIFTY: 40, SENSEX: 20, FINNIFTY: 25, MIDCPNIFTY: 50.

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

# Canonical Exchange Lot Sizes (per SEBI / Exchange rules)
INDEX_LOT_SIZES: Dict[str, int] = {
    "NIFTY": 65,
    "BANKNIFTY": 40,
    "SENSEX": 20,
    "FINNIFTY": 25,
    "MIDCPNIFTY": 50,
}


def get_exchange_lot_size(index_name: str) -> int:
    """Return the statutory exchange lot size for the given index."""
    sym = (index_name or "NIFTY").upper().strip()
    if "BANKNIFTY" in sym:
        return INDEX_LOT_SIZES["BANKNIFTY"]
    elif "SENSEX" in sym:
        return INDEX_LOT_SIZES["SENSEX"]
    elif "FINNIFTY" in sym:
        return INDEX_LOT_SIZES["FINNIFTY"]
    elif "MIDCPNIFTY" in sym:
        return INDEX_LOT_SIZES["MIDCPNIFTY"]
    return INDEX_LOT_SIZES.get(sym, 65)


def calculate_discrete_lots(
    total_capital: float,
    risk_budget_pct: float,  # e.g., 0.02 (2% of account)
    opt_premium: float,
    sl_points: float,
    index_name: str,
    sizing_recommendation: str = "FULL_SIZE",  # "FULL_SIZE", "HALF_SIZE", "ZERO_SUPPRESS"
) -> Tuple[int, str]:
    """Computes discrete lot count. Enforces Floor-or-Reject.
    
    Returns:
        (lots: int, sizing_tier: str)
    """
    if sizing_recommendation in {"ZERO_SUPPRESS", "REJECT", "VETO"}:
        return 0, "ZERO_SUPPRESS"

    lot_size = get_exchange_lot_size(index_name)
    risk_rupees = total_capital * max(0.0, float(risk_budget_pct))

    if sizing_recommendation == "HALF_SIZE":
        risk_rupees *= 0.5

    # Risk per lot = sl_points * lot_size
    risk_per_lot = max(float(sl_points) * lot_size, 1.0)

    # Capital margin per lot check
    margin_per_lot = float(opt_premium) * lot_size
    if margin_per_lot <= 0 or total_capital <= 0:
        return 0, "ZERO_SUPPRESS"

    lots_by_risk = math.floor(risk_rupees / risk_per_lot)
    lots_by_margin = math.floor(total_capital / margin_per_lot)

    lots = min(lots_by_risk, lots_by_margin)

    # Floor-or-Reject: Never round up
    if lots < 1:
        return 0, "REJECT_INSUFFICIENT_MARGIN"

    return int(lots), sizing_recommendation
