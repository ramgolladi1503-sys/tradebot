from typing import Dict, List, Optional
from core.research_registry.research_models import ResearchHypothesis


class HypothesisRegistry:
    """
    Manages and indexes ResearchHypothesis objects.
    Ensures that hypothesis IDs are unique and immutable.
    """
    
    def __init__(self) -> None:
        self._hypotheses: Dict[str, ResearchHypothesis] = {}

    def register(self, hypothesis: ResearchHypothesis) -> None:
        """Register a new hypothesis. Cannot overwrite existing ID."""
        if hypothesis.hypothesis_id in self._hypotheses:
            raise ValueError(f"Duplicate hypothesis ID: {hypothesis.hypothesis_id}")
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis

    def get(self, hypothesis_id: str) -> Optional[ResearchHypothesis]:
        """Retrieve a hypothesis by ID."""
        return self._hypotheses.get(hypothesis_id)

    def list_all(self) -> List[ResearchHypothesis]:
        """List all registered hypotheses."""
        return list(self._hypotheses.values())
