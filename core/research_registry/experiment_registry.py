from typing import Dict, List, Optional
from core.research_registry.research_models import ResearchExperiment


class ExperimentRegistry:
    """
    Manages ResearchExperiment instances.
    Ensures that experiment IDs are unique and that versions are appended immutably.
    """

    def __init__(self) -> None:
        self._experiments: Dict[str, ResearchExperiment] = {}

    def register(self, experiment: ResearchExperiment) -> None:
        """Register a new experiment."""
        if experiment.experiment_id in self._experiments:
            raise ValueError(f"Duplicate experiment ID: {experiment.experiment_id}")
        self._experiments[experiment.experiment_id] = experiment

    def get(self, experiment_id: str) -> Optional[ResearchExperiment]:
        """Retrieve an experiment by ID."""
        return self._experiments.get(experiment_id)

    def list_all(self) -> List[ResearchExperiment]:
        """List all experiments."""
        return list(self._experiments.values())
