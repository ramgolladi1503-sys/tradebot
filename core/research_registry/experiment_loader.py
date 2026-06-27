from typing import List
from core.research_registry.hypothesis_registry import HypothesisRegistry
from core.research_registry.experiment_registry import ExperimentRegistry
from core.research_registry.research_models import ResearchHypothesis, ResearchExperiment


class ExperimentLoader:
    """
    Dummy loader for research data.
    In a real implementation, this would load from a database or YAML files.
    """

    def __init__(self, hypothesis_registry: HypothesisRegistry, experiment_registry: ExperimentRegistry):
        self.hypothesis_registry = hypothesis_registry
        self.experiment_registry = experiment_registry

    def load_hypotheses(self, hypotheses: List[ResearchHypothesis]) -> None:
        """Load multiple hypotheses."""
        for hypothesis in hypotheses:
            self.hypothesis_registry.register(hypothesis)

    def load_experiments(self, experiments: List[ResearchExperiment]) -> None:
        """Load multiple experiments."""
        for experiment in experiments:
            self.experiment_registry.register(experiment)
