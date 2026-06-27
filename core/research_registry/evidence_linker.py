from typing import Optional
from core.research_registry.experiment_registry import ExperimentRegistry
from core.research_registry.research_models import ResearchEvidence


class EvidenceLinker:
    """Links downstream evidence systems using IDs only. Read-only context."""

    def __init__(self, experiment_registry: ExperimentRegistry):
        self.experiment_registry = experiment_registry

    def get_evidence(self, experiment_id: str) -> Optional[ResearchEvidence]:
        """Fetch the evidence block for an experiment."""
        exp = self.experiment_registry.get(experiment_id)
        if exp:
            return exp.evidence
        return None
