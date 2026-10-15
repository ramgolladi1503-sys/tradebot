"""
Session Chop Circuit Breaker Module.

Provides an isolated, deterministic, stateful circuit breaker to protect
high-velocity breakout strategies against mean-reverting chop regimes.

Invariants:
- Tracks consecutive losing trades (where realized option or spot PnL is negative)
  within a calendar session.
- If consecutive losses reach or exceed max_consecutive_losses, the breaker halts
  all further trade executions for the remainder of that calendar session.
- Resets cleanly and deterministically on calendar date transition.
- Fully serializable to WAL / state dictionary for seamless crash recovery.
"""

from typing import Tuple, Dict, Any, Optional

class SessionChopCircuitBreaker:
    def __init__(self, max_consecutive_losses: int = 2):
        self.max_consecutive_losses = max_consecutive_losses
        self.current_session_date: Optional[str] = None
        self.consecutive_losses: int = 0
        self.is_halted: bool = False
        self.rejection_reason: Optional[str] = None

    def evaluate_entry_permission(self, session_date: str) -> Tuple[bool, str]:
        """
        Evaluates whether a new trade entry is permitted for the given session date.
        """
        self._check_date_transition(session_date)
        if self.is_halted:
            return False, "BLOCKED_BY_CHOP_CIRCUIT_BREAKER"
        return True, "PERMITTED"

    def record_trade_exit(self, session_date: str, pnl_pts: Optional[float], exit_reason: str):
        """
        Records the outcome of a closed trade and updates consecutive loss counters.
        """
        self._check_date_transition(session_date)
        
        # If trade was unresolved or crashed, do not treat as an affirmative win
        if pnl_pts is None:
            # Unresolved trade increments risk or holds state
            return

        is_loss = (pnl_pts < 0.0) or ("STOP_LOSS" in exit_reason)
        if is_loss:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.is_halted = True
                self.rejection_reason = f"CONSECUTIVE_LOSS_LIMIT_REACHED_{self.consecutive_losses}"
        else:
            self.consecutive_losses = 0

    def _check_date_transition(self, session_date: str):
        if self.current_session_date != session_date:
            self.current_session_date = session_date
            self.consecutive_losses = 0
            self.is_halted = False
            self.rejection_reason = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state for WAL snapshotting."""
        return {
            "max_consecutive_losses": self.max_consecutive_losses,
            "current_session_date": self.current_session_date,
            "consecutive_losses": self.consecutive_losses,
            "is_halted": self.is_halted,
            "rejection_reason": self.rejection_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionChopCircuitBreaker":
        """Reconstruct state from WAL snapshot."""
        cb = cls(max_consecutive_losses=data.get("max_consecutive_losses", 2))
        cb.current_session_date = data.get("current_session_date")
        cb.consecutive_losses = data.get("consecutive_losses", 0)
        cb.is_halted = data.get("is_halted", False)
        cb.rejection_reason = data.get("rejection_reason")
        return cb
