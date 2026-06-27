from typing import Dict, List
from core.research_registry.hypothesis_registry import HypothesisRegistry
from core.research_registry.experiment_registry import ExperimentRegistry
from core.research_registry.research_models import ResearchExperiment


class DependencyGraph:
    """Builds a lineage DAG from Idea to Certification."""

    def __init__(self, hypothesis_registry: HypothesisRegistry, experiment_registry: ExperimentRegistry):
        self.hypothesis_registry = hypothesis_registry
        self.experiment_registry = experiment_registry

    def get_experiments_for_hypothesis(self, hypothesis_id: str) -> List[ResearchExperiment]:
        """Fetch all experiments linked to a specific hypothesis."""
        all_experiments = self.experiment_registry.list_all()
        return [exp for exp in all_experiments if exp.parent_hypothesis_id == hypothesis_id]

    def build_full_lineage_graph(self) -> Dict[str, dict]:
        """Builds a complete DAG representing the lineage for all hypotheses."""
        graph = {}
        hypotheses = self.hypothesis_registry.list_all()
        
        for hyp in hypotheses:
            experiments = self.get_experiments_for_hypothesis(hyp.hypothesis_id)
            exp_details = []
            for exp in experiments:
                versions = [v.version_id for v in exp.versions]
                exp_details.append({
                    "experiment_id": exp.experiment_id,
                    "versions": versions,
                    "evidence_links": {
                        "strategy": exp.evidence.strategy_registry_id,
                        "truth": exp.evidence.truth_engine_report_id,
                        "outcome": exp.evidence.outcome_evidence_id,
                        "statistics": exp.evidence.statistical_validation_id,
                        "certification": exp.evidence.certification_id
                    }
                })
            
            graph[hyp.hypothesis_id] = {
                "title": hyp.title,
                "experiments": exp_details
            }
            
        return graph
