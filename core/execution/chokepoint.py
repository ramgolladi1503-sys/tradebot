from __future__ import annotations

import os
import time
from typing import Any, Optional

from config import config as cfg
from core.approval_store import consume_valid_approval
from core.audit_log import append_event


class ApprovalMissingOrInvalid(RuntimeError):
    def __init__(self, reason: str, intent_hash: str, mode: str):
        super().__init__(reason)
        self.reason = reason
        self.intent_hash = intent_hash
        self.mode = mode


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


def _intent_hash(order_intent: Any) -> str:
    if hasattr(order_intent, "intent_hash") and callable(order_intent.intent_hash):
        return str(order_intent.intent_hash())
    if hasattr(order_intent, "order_intent_hash") and callable(order_intent.order_intent_hash):
        return str(order_intent.order_intent_hash())
    if hasattr(order_intent, "intent_hash"):
        return str(getattr(order_intent, "intent_hash"))
    raise ApprovalMissingOrInvalid("approval_hash_missing", "", "UNKNOWN")


def _audit(intent_hash: str, mode: str, ok: bool, reason: str) -> None:
    payload = {
        "event": "ORDER_APPROVAL_CHOKEPOINT",
        "intent_hash": intent_hash,
        "mode": mode,
        "approved": int(ok),
        "reason": reason,
    }
    try:
        append_event(payload)
    except Exception as exc:
        print(f"[ORDER_APPROVAL_CHOKEPOINT_AUDIT_ERROR] {exc} | payload={payload}")


def require_approval_or_abort(
    order_intent: Any,
    mode: str,
    now: Optional[float] = None,
    approver: Optional[str] = None,
    ttl: Optional[int] = None,
) -> str:
    mode_upper = str(mode or getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    hash_value = _intent_hash(order_intent)
    now_epoch = float(now if now is not None else time.time())

    if mode_upper == "LIVE" and os.getenv("LIVE_TRADING_ENABLED", "false").lower() != "true":
        reason = "live_trading_env_disabled"
        _audit(hash_value, mode_upper, False, reason)
        raise ApprovalMissingOrInvalid(reason, hash_value, mode_upper)

    if not bool(getattr(cfg, "MANUAL_APPROVAL", True)):
        reason = "manual_approval_disabled"
        _audit(hash_value, mode_upper, False, reason)
        raise ApprovalMissingOrInvalid(reason, hash_value, mode_upper)

    ok, reason = consume_valid_approval(
        order_intent_hash=hash_value,
        approver_id=approver,
        ttl_sec=ttl,
        now=now_epoch,
        require_armed=_requires_armed_approval(mode_upper),
    )
    if not ok:
        reason = f"manual_approval_required:{reason}"
        _audit(hash_value, mode_upper, False, reason)
        raise ApprovalMissingOrInvalid(reason, hash_value, mode_upper)
    _audit(hash_value, mode_upper, True, "approved_and_consumed")
    return hash_value
