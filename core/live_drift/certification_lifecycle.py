from datetime import datetime
from typing import Dict, List
from core.live_drift.drift_types import LifecycleState
from core.live_drift.drift_models import LifecycleTransition


class CertificationLifecycle:
    """Manages strategy certification states according to rigid state machine."""

    VALID_TRANSITIONS = {
        LifecycleState.PRODUCTION_CANDIDATE: {LifecycleState.WARNING, LifecycleState.UNDER_REVIEW},
        LifecycleState.WARNING: {LifecycleState.UNDER_REVIEW, LifecycleState.PRODUCTION_CANDIDATE, LifecycleState.SUSPENDED},
        LifecycleState.UNDER_REVIEW: {LifecycleState.PRODUCTION_CANDIDATE, LifecycleState.SUSPENDED},
        LifecycleState.SUSPENDED: {LifecycleState.REVOKED},
        # Recovery path: REVOKED -> NEW RESEARCH (not handled in this state machine directly)
        LifecycleState.REVOKED: set()
    }

    def __init__(self):
        self._states: Dict[str, LifecycleState] = {}
        self._history: Dict[str, List[LifecycleTransition]] = {}

    def get_state(self, strategy_id: str) -> LifecycleState:
        return self._states.get(strategy_id, LifecycleState.PRODUCTION_CANDIDATE)
        
    def transition(self, strategy_id: str, to_state: LifecycleState, reason: str) -> LifecycleTransition:
        current_state = self.get_state(strategy_id)
        
        if to_state not in self.VALID_TRANSITIONS.get(current_state, set()):
            raise ValueError(f"Invalid transition from {current_state} to {to_state}")
            
        transition = LifecycleTransition(
            strategy_id=strategy_id,
            timestamp=datetime.utcnow(),
            from_state=current_state,
            to_state=to_state,
            reason=reason
        )
        
        self._states[strategy_id] = to_state
        if strategy_id not in self._history:
            self._history[strategy_id] = []
        self._history[strategy_id].append(transition)
        
        return transition
        
    def get_history(self, strategy_id: str) -> List[LifecycleTransition]:
        return self._history.get(strategy_id, [])
