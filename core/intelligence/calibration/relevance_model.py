from dataclasses import dataclass
from typing import List
from core.intelligence.calibration.factors import Factor

@dataclass
class RelevanceModel:
    """Consolidated relevance container for an intelligence event."""
    factors: List[Factor]

    def has_execution_influence(self) -> bool:
        """Returns True ONLY if ALL factors are calibrated and allow execution influence."""
        if not self.factors:
            return False
        return all(f.execution_influence_allowed for f in self.factors)

    def has_ranking_influence(self) -> bool:
        """Returns True ONLY if ALL factors are calibrated and allow ranking influence."""
        if not self.factors:
            return False
        return all(f.ranking_influence_allowed for f in self.factors)
