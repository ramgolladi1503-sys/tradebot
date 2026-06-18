import time
from core.feed_freshness import get_feed_freshness
from core.feed_freshness_gate import assess_feed_freshness_gate

class VixSafetyGate:
    def __init__(self, warning_threshold: float = 22.0, kill_threshold: float = 25.0) -> None:
        self.warning_threshold = warning_threshold
        self.kill_threshold = kill_threshold
        self.current_vix = 15.0 # Default safe value
        
    def update_vix(self, new_vix_value: float) -> None:
        """Called by live tick feed when INDIA VIX updates"""
        self.current_vix = new_vix_value
        
    def _is_stale(self) -> tuple[bool, str]:
        """PRODUCTION UPGRADE: Respect existing feed freshness architecture"""
        try:
            freshness_status = get_feed_freshness()
            decision = assess_feed_freshness_gate(freshness_status)
            
            if not decision.allowed_for_paper_execution and not decision.allowed_for_live_execution:
                blockers = ", ".join(decision.blockers)
                return True, f"Global Feed Staleness Detected: {blockers}"
                
            return False, ""
        except Exception as e:
            return True, f"Error checking feed freshness: {e}"
        
    def get_position_modifier(self) -> float:
        """
        Returns 1.0 (Full Size), 0.5 (Half Size), or 0.0 (Kill Switch Blocked)
        """
        is_stale, _ = self._is_stale()
        if is_stale:
            return 0.0 # Block all trades if feed is broken
            
        if self.current_vix >= self.kill_threshold:
            return 0.0 # Extreme volatility, block all entries
        elif self.current_vix >= self.warning_threshold:
            return 0.5 # High volatility, cut size in half
        else:
            return 1.0 # Safe
            
    def can_trade(self) -> tuple[bool, str]:
        is_stale, stale_reason = self._is_stale()
        if is_stale:
            return False, stale_reason
            
        if self.current_vix >= self.kill_threshold:
            return False, f"VIX Kill Switch Active ({self.current_vix} > {self.kill_threshold})"
            
        return True, "Safe"
