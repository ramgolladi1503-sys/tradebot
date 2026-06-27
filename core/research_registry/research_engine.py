from datetime import datetime
from typing import List, Optional
from core.research_registry.hypothesis_registry import HypothesisRegistry
from core.research_registry.experiment_registry import ExperimentRegistry
from core.research_registry.research_models import (
    ResearchHypothesis, ResearchExperiment, ExperimentVersion, 
    ResearchDecision, ResearchRegistryReport
)
from core.research_registry.promotion_policy import PromotionPolicy
from core.research_registry.validation import ResearchRegistryValidator


class ResearchEngine:
    """Orchestrates loading, tracking, validation, and decision logging."""

    def __init__(self):
        self.hypothesis_registry = HypothesisRegistry()
        self.experiment_registry = ExperimentRegistry()
        self._decisions: List[ResearchDecision] = []

    def register_hypothesis(self, hypothesis: ResearchHypothesis) -> None:
        self.hypothesis_registry.register(hypothesis)

    def register_experiment(self, experiment: ResearchExperiment) -> None:
        self.experiment_registry.register(experiment)
        
    def add_experiment_version(self, experiment_id: str, version: ExperimentVersion) -> None:
        exp = self.experiment_registry.get(experiment_id)
        if not exp:
            raise ValueError(f"Experiment {experiment_id} not found.")
        # Ensure version ID is unique
        if any(v.version_id == version.version_id for v in exp.versions):
            raise ValueError(f"Duplicate version ID: {version.version_id}")
            
        exp.versions.append(version)
        
    def evaluate_experiment(self, experiment_id: str, author: str) -> Optional[ResearchDecision]:
        exp = self.experiment_registry.get(experiment_id)
        if not exp or not exp.versions:
            return None
            
        # Evaluate the latest version
        latest_version = max(exp.versions, key=lambda v: v.created_timestamp)
        recommendation = PromotionPolicy.evaluate(latest_version)
        
        decision = ResearchDecision(
            experiment_id=experiment_id,
            version_id=latest_version.version_id,
            decision_timestamp=datetime.utcnow(),
            author=author,
            recommendation=recommendation
        )
        self._decisions.append(decision)
        return decision

    def validate_state(self) -> None:
        ResearchRegistryValidator.assert_no_orphans(self.experiment_registry, self.hypothesis_registry)
        ResearchRegistryValidator.assert_versions_valid(self.experiment_registry)
        ResearchRegistryValidator.assert_no_execution_influence()

    def generate_report_model(self) -> ResearchRegistryReport:
        self.validate_state()
        return ResearchRegistryReport(
            timestamp=datetime.utcnow(),
            hypotheses=self.hypothesis_registry.list_all(),
            experiments=self.experiment_registry.list_all(),
            decisions=self._decisions
        )
