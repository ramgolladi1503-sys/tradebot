from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.feed_recovery_coordinator import FeedRecoveryState


@dataclass(frozen=True)
class RecoveryBlockDecision:
    allowed: bool
    state: str
    reason: str
    details: dict[str, Any]

    def as_tuple(self) -> tuple[bool, str, str, dict[str, Any]]:
        """Returns (allowed, reject_reason, state_name, details) for compatibility."""
        reject_reason = "ok" if self.allowed else f"feed_state_{self.state}"
        return self.allowed, reject_reason, self.state, self.details


def evaluate_recovery_block(recovery_state: FeedRecoveryState, group_key: str = "") -> RecoveryBlockDecision | None:
    """
    Evaluates the recovery state and returns a blocking RecoveryBlockDecision if the feed
    is not in a recovered/healthy state. Returns None if recovery state is OK, meaning
    freshness checks can proceed.
    """
    details = {"group_key": group_key} if group_key else {}
    
    if recovery_state.auth_required:
        details["reason"] = "FEED_AUTH_REQUIRED"
        return RecoveryBlockDecision(False, "DOWN", "FEED_AUTH_REQUIRED", details)
    if recovery_state.terminal_failure:
        details["reason"] = "FEED_RECOVERY_TERMINAL_FAILURE"
        return RecoveryBlockDecision(False, "DOWN", "FEED_RECOVERY_TERMINAL_FAILURE", details)
    if recovery_state.recovery_blocked:
        details["reason"] = "FEED_RECOVERY_BLOCKED"
        return RecoveryBlockDecision(False, "DOWN", "FEED_RECOVERY_BLOCKED", details)
    if recovery_state.recovery_in_progress:
        details["reason"] = "FEED_RECOVERY_IN_PROGRESS"
        return RecoveryBlockDecision(False, "DOWN", "FEED_RECOVERY_IN_PROGRESS", details)
        
    return None
