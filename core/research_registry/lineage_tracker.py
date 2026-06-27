from typing import List
from core.research_registry.research_models import ResearchExperiment, ExperimentVersion


class LineageTracker:
    """Tracks historical paths and parameter evolutions within an experiment."""

    @staticmethod
    def get_version_history(experiment: ResearchExperiment) -> List[ExperimentVersion]:
        """Return the immutable versions of an experiment, sorted chronologically."""
        return sorted(experiment.versions, key=lambda v: v.created_timestamp)

    @staticmethod
    def extract_parameter_evolution(experiment: ResearchExperiment) -> List[dict]:
        """Extract how parameters changed across versions."""
        evolution = []
        versions = LineageTracker.get_version_history(experiment)
        
        for version in versions:
            evolution.append({
                "version_id": version.version_id,
                "timestamp": version.created_timestamp,
                "stage": version.stage.name,
                "parameters": version.parameters.parameters
            })
            
        return evolution
