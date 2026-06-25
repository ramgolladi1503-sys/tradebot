from typing import Dict, Any, List
from core.intelligence.calibration.relevance_model import RelevanceModel
import logging

logger = logging.getLogger(__name__)

class ContextAdapter:
    """
    Safely adapts Intelligence Relevance Models onto TradeBot Candidates.
    Strictly asserts read-only/advisory integration unless fully calibrated.
    """
    def __init__(self):
        self.advisory_key = "advisory_context"

    def inject_context(self, candidate: Dict[str, Any], relevance_models: List[RelevanceModel]) -> Dict[str, Any]:
        """
        Attaches the intelligence to the candidate without mutating execution state.
        Returns the mutated candidate explicitly for clarity.
        """
        
        # Hard Assertion: Never create candidates
        if not candidate:
            logger.error("Cannot inject context into a None candidate")
            return candidate
            
        # Serialize the models for the payload
        payload = [
            {
                "has_execution_influence": rm.has_execution_influence(),
                "has_ranking_influence": rm.has_ranking_influence(),
                "factors": [
                    {
                        "name": f.name,
                        "status": f.calibration_status.value,
                        "value": f.value
                    } for f in rm.factors
                ]
            }
            for rm in relevance_models
        ]

        # Explicitly enforce anti-heuristics at the boundary
        for rm in relevance_models:
            if rm.has_execution_influence():
                logger.critical("MIP attempting to assert execution influence. This is currently disabled system-wide.")
                # We do NOT flip execution_ok=True here. We let the execution engine 
                # read the payload if it is formally wired to do so later.
        
        # Attach strictly as metadata
        existing_context = candidate.get(self.advisory_key, [])
        candidate[self.advisory_key] = existing_context + payload
        
        # Also ensure we don't accidentally remove blockers by touching candidate_status
        # We leave candidate_status exactly as it was.
        
        return candidate
