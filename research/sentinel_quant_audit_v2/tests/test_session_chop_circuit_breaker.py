import pytest

class SessionChopCircuitBreaker:
    """
    Challenger Session Chop Circuit Breaker.
    Invariant:
    - Tracks consecutive stop-loss or negative PnL exits within a calendar session.
    - If consecutive losses >= max_consecutive_losses (default 2), trips circuit breaker.
    - Once tripped, all subsequent entry proposals for that session are rejected with BLOCKED_BY_CHOP_CIRCUIT_BREAKER.
    - Resets automatically on date transition.
    """
    def __init__(self, max_consecutive_losses=2):
        self.max_consecutive_losses = max_consecutive_losses
        self.current_session_date = None
        self.consecutive_losses = 0
        self.is_halted = False
        self.rejection_reason = None

    def evaluate_entry_permission(self, session_date: str) -> tuple[bool, str]:
        if self.current_session_date != session_date:
            # New session reset
            self.current_session_date = session_date
            self.consecutive_losses = 0
            self.is_halted = False
            self.rejection_reason = None
            
        if self.is_halted:
            return False, "BLOCKED_BY_CHOP_CIRCUIT_BREAKER"
        return True, "PERMITTED"

    def record_trade_exit(self, session_date: str, pnl_pts: float, exit_reason: str):
        if self.current_session_date != session_date:
            self.current_session_date = session_date
            self.consecutive_losses = 0
            self.is_halted = False
            
        is_loss = (pnl_pts < 0) or ("STOP_LOSS" in exit_reason)
        if is_loss:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.is_halted = True
                self.rejection_reason = f"CONSECUTIVE_LOSS_LIMIT_REACHED_{self.consecutive_losses}"
        else:
            self.consecutive_losses = 0

def test_circuit_breaker_permits_initial_trades():
    cb = SessionChopCircuitBreaker(max_consecutive_losses=2)
    ok, reason = cb.evaluate_entry_permission("2026-10-14")
    assert ok is True
    assert reason == "PERMITTED"

def test_circuit_breaker_trips_on_two_consecutive_losses():
    cb = SessionChopCircuitBreaker(max_consecutive_losses=2)
    date = "2026-10-14"
    
    # Trade 1: Win (+4.75 pts)
    cb.record_trade_exit(date, 4.75, "RUNNER_HWM_TRAILING_EXIT")
    ok, _ = cb.evaluate_entry_permission(date)
    assert ok is True
    
    # Trade 2: Win (+2.55 pts)
    cb.record_trade_exit(date, 2.55, "TRAILING_STOP_HIT")
    ok, _ = cb.evaluate_entry_permission(date)
    assert ok is True
    
    # Trade 3: Loss (-0.85 pts, STOP_LOSS_HIT)
    cb.record_trade_exit(date, -0.85, "STOP_LOSS_HIT")
    ok, _ = cb.evaluate_entry_permission(date)
    assert ok is True, "First loss should not trip breaker"
    
    # Trade 4: Loss (-34.60 pts, OPTION_NATIVE_STOP_LOSS_HIT)
    cb.record_trade_exit(date, -34.60, "OPTION_NATIVE_STOP_LOSS_HIT")
    
    # Trade 5 attempt: MUST BE BLOCKED
    ok, reason = cb.evaluate_entry_permission(date)
    assert ok is False, "Second consecutive loss must trip circuit breaker"
    assert reason == "BLOCKED_BY_CHOP_CIRCUIT_BREAKER"
    
    # Subsequent trade attempts on same date remain blocked
    ok, _ = cb.evaluate_entry_permission(date)
    assert ok is False

def test_circuit_breaker_resets_on_new_date():
    cb = SessionChopCircuitBreaker(max_consecutive_losses=2)
    # Trip on Oct 14
    cb.record_trade_exit("2026-10-14", -5.0, "STOP_LOSS_HIT")
    cb.record_trade_exit("2026-10-14", -10.0, "STOP_LOSS_HIT")
    ok, _ = cb.evaluate_entry_permission("2026-10-14")
    assert ok is False
    
    # New day: Oct 15
    ok, reason = cb.evaluate_entry_permission("2026-10-15")
    assert ok is True, "New session date must reset circuit breaker"
    assert reason == "PERMITTED"

def test_circuit_breaker_handles_intermittent_wins():
    cb = SessionChopCircuitBreaker(max_consecutive_losses=2)
    date = "2026-10-15"
    
    # Loss 1
    cb.record_trade_exit(date, -5.0, "STOP_LOSS_HIT")
    # Win (resets counter)
    cb.record_trade_exit(date, 10.0, "TARGET_HIT")
    # Loss 2
    cb.record_trade_exit(date, -4.0, "STOP_LOSS_HIT")
    
    # Should STILL be permitted because losses were not consecutive
    ok, _ = cb.evaluate_entry_permission(date)
    assert ok is True, "Intermittent win must reset consecutive loss count"
