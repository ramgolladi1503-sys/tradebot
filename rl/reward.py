from __future__ import annotations

from typing import Any, Dict, Tuple

from config import config as cfg


def simulate_fill(row: Dict[str, Any]) -> Tuple[bool, float | None]:
    """
    Simulate fill using stored bid/ask snapshots only.
    BUY fills if limit >= ask; SELL fills if limit <= bid.
    We approximate limit at ask/bid for BUY/SELL since DecisionEvent doesn't
    store explicit limit_price.
    """
    bid = row.get("bid")
    ask = row.get("ask")
    side = (row.get("side") or "BUY").upper()
    if bid is None or ask is None:
        return False, None
    if side == "BUY":
        return True, float(ask)
    if side == "SELL":
        return True, float(bid)
    return False, None


def compute_reward(row: Dict[str, Any], action_mult: float, filled: bool, fill_price: float | None) -> float:
    """
    CRO-safe reward:
    - Base PnL uses pnl_horizon_15m if available, else pnl_horizon_5m, else 0
    - Penalize drawdown and slippage
    - Action multiplier scales risk
    """
    mode = getattr(cfg, "RL_REWARD_MODE", "CRO_SAFE").upper()

    pnl = row.get("pnl_horizon_15m")
    if pnl is None:
        pnl = row.get("pnl_horizon_5m")
    pnl = float(pnl or 0.0)

    dd = float(row.get("drawdown_pct") or 0.0)
    slippage = float(row.get("slippage_vs_mid") or 0.0)
    spread = float(row.get("spread_pct") or 0.0)
    shock = float(row.get("shock_score") or 0.0)

    if not filled or action_mult <= 0:
        return 0.0

    reward = pnl * action_mult

    # Execution-aware penalties
    reward -= abs(slippage) * 0.5
    reward -= spread * 2.0

    # Risk penalties
    reward -= abs(dd) * 10.0
    reward -= shock * 2.0

    if mode == "EXEC_AWARE":
        reward -= abs(slippage) * 1.0
        reward -= spread * 4.0

    return reward
