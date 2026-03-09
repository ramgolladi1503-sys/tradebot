from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from config import config as cfg
from core.approval_store import consume_valid_approval
from core.market_context import derive_market_context
from core.orders.order_intent import OrderIntent
from core.regime_monitor import get_regime_monitor_status
from core.survival_gates import SurvivalGates


@dataclass(frozen=True)
class ExecutionGuardDecision:
    allowed: bool
    reason_code: str
    reason: str
    mode: str
    planning_only: bool
    context: dict[str, Any] = field(default_factory=dict)

    def as_tuple(self):
        return bool(self.allowed), str(self.reason)


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


def _is_regime_dependent_strategy(strategy_name: str | None) -> bool:
    text = str(strategy_name or "").strip().upper()
    if not text:
        return False
    hints = list(getattr(cfg, "REGIME_DEPENDENT_STRATEGY_HINTS", []) or [])
    return any(str(h).strip().upper() in text for h in hints if str(h).strip())


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
    def __init__(self, risk_state=None, survival_gates: SurvivalGates | None = None):
        self.risk_state = risk_state
        self.survival_gates = survival_gates or SurvivalGates()
        self.last_decision = None

    def _min_conf(self, regime):
        min_conf = getattr(cfg, "ML_MIN_PROBA", 0.6)
        mult = getattr(cfg, "REGIME_PROBA_MULT", {}).get(regime or "NEUTRAL", 1.0)
        return min_conf * mult

    @staticmethod
    def _reason_code(reason: str) -> str:
        text = str(reason or "").strip()
        if not text:
            return "UNKNOWN"
        mapping = {
            "Approved": "APPROVED",
            "Planning only": "PLANNING_ONLY_MODE",
            "Market closed": "MARKET_CLOSED",
            "Execution not allowed": "EXECUTION_NOT_ALLOWED",
            "Survival gate breach": "SURVIVAL_GATE_BREACH",
            "Low confidence": "LOW_CONFIDENCE",
            "Insufficient capital": "INSUFFICIENT_CAPITAL",
            "Regime mismatch": "REGIME_MISMATCH",
        }
        return mapping.get(text, text.upper().replace(" ", "_"))

    def _market_context(self, *, market_data=None, mode=None):
        payload = {}
        if isinstance(market_data, Mapping):
            nested = market_data.get("market_context")
            if isinstance(nested, Mapping):
                payload.update(dict(nested))
            if "market_open" in market_data:
                payload["market_open"] = market_data.get("market_open")
            if "execution_mode" in market_data:
                payload["execution_mode"] = market_data.get("execution_mode")
            if "segment" in market_data:
                payload["segment"] = market_data.get("segment")
        if mode is not None:
            payload["execution_mode"] = mode
        if "execution_mode" not in payload:
            payload["execution_mode"] = getattr(cfg, "EXECUTION_MODE", "SIM")
        return derive_market_context(payload)

    def _requested_mode(self, *, market_data=None, mode=None) -> str:
        if mode is not None:
            return str(mode).strip().upper()
        if isinstance(market_data, Mapping):
            nested = market_data.get("market_context")
            if isinstance(nested, Mapping) and nested.get("execution_mode") is not None:
                return str(nested.get("execution_mode")).strip().upper()
            if market_data.get("execution_mode") is not None:
                return str(market_data.get("execution_mode")).strip().upper()
        return str(getattr(cfg, "EXECUTION_MODE", "SIM")).strip().upper()

    def _decision(self, *, allowed: bool, reason: str, mode: str, planning_only: bool, context=None):
        decision = ExecutionGuardDecision(
            allowed=bool(allowed),
            reason_code=self._reason_code(reason),
            reason=str(reason),
            mode=str(mode),
            planning_only=bool(planning_only),
            context=dict(context or {}),
        )
        self.last_decision = decision
        return decision

    def evaluate(self, trade, portfolio, regime, *, market_data=None, mode=None):
        market_ctx = self._market_context(market_data=market_data, mode=mode)
        requested_mode = self._requested_mode(market_data=market_data, mode=mode)
        planning_only = bool(
            market_ctx.planning_only
            or getattr(trade, "planning_only", False)
            or (not bool(getattr(trade, "execution_allowed", True)))
        )
        if requested_mode == "LIVE":
            if bool(getattr(cfg, "LIVE_FAIL_CLOSED_ON_MARKET_CLOSED", True)) and (not bool(market_ctx.is_market_open)):
                return self._decision(
                    allowed=False,
                    reason="Market closed",
                    mode=requested_mode,
                    planning_only=False,
                    context={"require_live_quotes": bool(market_ctx.require_live_quotes)},
                )
            if bool(getattr(cfg, "ENFORCE_EXECUTION_ALLOWED_FLAG", True)) and (
                not bool(getattr(trade, "execution_allowed", True))
            ):
                return self._decision(
                    allowed=False,
                    reason="Execution not allowed",
                    mode=requested_mode,
                    planning_only=False,
                    context={"trade_reason": getattr(trade, "reason", None)},
                )
        if getattr(trade, "tradable", True) is False:
            reasons = list(getattr(trade, "tradable_reasons_blocking", []) or [])
            msg = "non_tradable"
            if reasons:
                msg = f"non_tradable:{'|'.join(reasons)}"
            return self._decision(
                allowed=False,
                reason=msg,
                mode=market_ctx.mode,
                planning_only=planning_only,
                context={"tradable_reasons_blocking": reasons},
            )

        survival_decision = self.survival_gates.evaluate(
            trade=trade,
            portfolio=portfolio,
            risk_state=self.risk_state,
            market_data=market_data if isinstance(market_data, Mapping) else None,
        )
        base_context = dict(survival_decision.context or {})
        if not bool(survival_decision.allowed_entries):
            return self._decision(
                allowed=False,
                reason="Survival gate breach",
                mode=market_ctx.mode,
                planning_only=planning_only,
                context=base_context,
            )

        if bool(getattr(cfg, "REGIME_MONITOR_ENABLED", True)):
            regime_status = get_regime_monitor_status(prefer_disk=False)
            severe_collapse = bool(regime_status.get("severe"))
            collapsed = bool(regime_status.get("collapsed"))
            if severe_collapse and bool(getattr(cfg, "REGIME_MONITOR_P0_ON_SEVERE", True)):
                return self._decision(
                    allowed=False,
                    reason="Regime monitor severe collapse",
                    mode=market_ctx.mode,
                    planning_only=planning_only,
                    context={"regime_monitor": regime_status},
                )
            if collapsed and _is_regime_dependent_strategy(getattr(trade, "strategy", None)):
                size_mult = float(getattr(cfg, "REGIME_MONITOR_SIZE_MULT_ON_COLLAPSE", 0.5))
                if bool(getattr(cfg, "REGIME_MONITOR_BLOCK_ON_COLLAPSE", True)):
                    return self._decision(
                        allowed=False,
                        reason="Regime monitor collapse",
                        mode=market_ctx.mode,
                        planning_only=planning_only,
                        context={**base_context, "regime_monitor": regime_status},
                    )
                context = {**base_context, "regime_monitor": regime_status, "size_multiplier": max(0.0, min(1.0, size_mult))}
            else:
                context = dict(base_context)
        else:
            context = dict(base_context)
        if float(survival_decision.size_multiplier) < 1.0:
            context["size_multiplier"] = max(
                0.0,
                min(1.0, float(context.get("size_multiplier", 1.0)) * float(survival_decision.size_multiplier)),
            )
        if self.risk_state:
            ok, reason = self.risk_state.approve(trade)
            if not ok:
                return self._decision(
                    allowed=False,
                    reason=f"RiskState: {reason}",
                    mode=market_ctx.mode,
                    planning_only=planning_only,
                )
        min_conf = self._min_conf(regime)
        if trade.confidence < min_conf:
            return self._decision(
                allowed=False,
                reason="Low confidence",
                mode=market_ctx.mode,
                planning_only=planning_only,
                context={"trade_confidence": trade.confidence, "min_confidence": min_conf},
            )

        if trade.capital_at_risk > portfolio.get("capital", 0):
            return self._decision(
                allowed=False,
                reason="Insufficient capital",
                mode=market_ctx.mode,
                planning_only=planning_only,
                context={"capital_at_risk": trade.capital_at_risk, "capital": portfolio.get("capital", 0)},
            )

        if regime == "RANGE" and trade.strategy == "TREND":
            return self._decision(
                allowed=False,
                reason="Regime mismatch",
                mode=market_ctx.mode,
                planning_only=planning_only,
                context={"regime": regime, "strategy": trade.strategy},
            )

        if planning_only and bool(getattr(cfg, "EXECUTION_GUARD_ALLOW_PLANNING", True)):
            return self._decision(
                allowed=True,
                reason="Planning only",
                mode=market_ctx.mode,
                planning_only=True,
                context={**context, "execution_allowed": bool(getattr(trade, "execution_allowed", True))},
            )
        return self._decision(
            allowed=True,
            reason="Approved",
            mode=market_ctx.mode,
            planning_only=planning_only,
            context=context,
        )

    def validate(self, trade, portfolio, regime, *, market_data=None, mode=None):
        return self.evaluate(
            trade,
            portfolio,
            regime,
            market_data=market_data,
            mode=mode,
        ).as_tuple()
