from __future__ import annotations

import os
from typing import Optional, Tuple

from config import config as cfg
from core.approval_store import consume_valid_approval
from core.orders.order_intent import OrderIntent


def _required_approval_modes() -> set[str]:
    raw = str(getattr(cfg, "APPROVAL_REQUIRED_MODES", "PAPER,LIVE") or "PAPER,LIVE")
    return {m.strip().upper() for m in raw.split(",") if m.strip()}


def _requires_armed_approval(mode: str) -> bool:
    mode_upper = str(mode or "").upper()
    if mode_upper == "LIVE":
        fallback = os.getenv("LIVE_REQUIRE_ARMED_APPROVAL", "true").lower() == "true"
        return bool(getattr(cfg, "LIVE_REQUIRE_ARMED_APPROVAL", fallback))
    if mode_upper == "PAPER":
        fallback = os.getenv("PAPER_REQUIRE_ARMED_APPROVAL", "false").lower() == "true"
        return bool(getattr(cfg, "PAPER_REQUIRE_ARMED_APPROVAL", fallback))
    if mode_upper == "SIM":
        fallback = os.getenv("SIM_REQUIRE_ARMED_APPROVAL", "false").lower() == "true"
        return bool(getattr(cfg, "SIM_REQUIRE_ARMED_APPROVAL", fallback))
    return False


def must_have_valid_approval(order_intent_hash: str, approver: Optional[str] = None, ttl: Optional[int] = None, mode: Optional[str] = None) -> Tuple[bool, str]:
    if not bool(getattr(cfg, "MANUAL_APPROVAL", True)):
        if str(mode or getattr(cfg, "EXECUTION_MODE", "")).upper() == "LIVE":
            return False, "manual_approval_required_for_live"
        return True, "manual_approval_disabled"
    mode_upper = str(mode or getattr(cfg, "EXECUTION_MODE", "")).upper()
    if mode_upper == "LIVE":
        if os.getenv("LIVE_TRADING_ENABLED", "false").lower() != "true":
            return False, "live_trading_env_disabled"
    required_modes = _required_approval_modes()
    if mode_upper and mode_upper not in required_modes:
        return True, "approval_not_required_for_mode"
    ok, reason = consume_valid_approval(
        order_intent_hash=order_intent_hash,
        approver_id=approver,
        ttl_sec=ttl,
        require_armed=_requires_armed_approval(mode_upper),
    )
    if not ok:
        return False, f"manual_approval_required:{reason}"
    return True, "approved_and_consumed"


class ExecutionGuard:
    def __init__(self, risk_state=None):
        self.risk_state = risk_state

    def _min_conf(self, regime):
        min_conf = getattr(cfg, "ML_MIN_PROBA", 0.6)
        mult = getattr(cfg, "REGIME_PROBA_MULT", {}).get(regime or "NEUTRAL", 1.0)
        return min_conf * mult

    def validate(self, trade, portfolio, regime):
        if getattr(trade, "tradable", True) is False:
            reasons = list(getattr(trade, "tradable_reasons_blocking", []) or [])
            msg = "non_tradable"
            if reasons:
                msg = f"non_tradable:{'|'.join(reasons)}"
            return False, msg
        if self.risk_state:
            ok, reason = self.risk_state.approve(trade)
            if not ok:
                return False, f"RiskState: {reason}"
        min_conf = self._min_conf(regime)
        if trade.confidence < min_conf:
            return False, "Low confidence"

        if trade.capital_at_risk > portfolio.get("capital", 0):
            return False, "Insufficient capital"

        if regime == "RANGE" and trade.strategy == "TREND":
            return False, "Regime mismatch"

        return True, "Approved"
