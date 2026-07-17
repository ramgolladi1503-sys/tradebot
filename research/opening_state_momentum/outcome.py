from typing import List, Union
from datetime import date
import pandas as pd
from research.opening_state_momentum.partition import PartitionGuard

class HoldoutLockedError(Exception):
    pass

class OutcomeEngine:
    def __init__(self, guard: PartitionGuard):
        self.guard = guard
        
    def evaluate_session(self, session_date: Union[str, date, pd.Timestamp]):
        # Before doing any work, check the guard
        try:
            self.guard.check_access(session_date, "evaluate_outcome")
        except Exception as e:
            raise HoldoutLockedError("HOLDOUT_LOCKED") from e
            
        # Minimal implementation, not calculating returns
        pass
        
    def evaluate_batch(self, session_dates: List[Union[str, date, pd.Timestamp]]):
        for d in session_dates:
            try:
                self.guard.check_access(d, "evaluate_outcome")
            except Exception as e:
                raise HoldoutLockedError("HOLDOUT_LOCKED") from e
        pass
