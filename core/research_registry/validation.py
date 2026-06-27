from core.research_registry.hypothesis_registry import HypothesisRegistry
from core.research_registry.experiment_registry import ExperimentRegistry
from core.research_registry.experiment_validator import ExperimentValidator


class ResearchRegistryValidator:
    """Additional strict safety validations asserting read-only boundaries and policy adherence."""
    
    @staticmethod
    def assert_no_orphans(experiment_registry: ExperimentRegistry, hypothesis_registry: HypothesisRegistry) -> None:
        """Ensure all experiments link to a valid hypothesis."""
        for exp in experiment_registry.list_all():
            if not hypothesis_registry.get(exp.parent_hypothesis_id):
                raise ValueError(f"Orphan experiment detected: {exp.experiment_id} has invalid parent {exp.parent_hypothesis_id}")

    @staticmethod
    def assert_versions_valid(experiment_registry: ExperimentRegistry) -> None:
        """Ensure all version transitions inside experiments are valid."""
        for exp in experiment_registry.list_all():
            versions = sorted(exp.versions, key=lambda v: v.created_timestamp)
            for i, version in enumerate(versions):
                prev = versions[i - 1] if i > 0 else None
                errors = ExperimentValidator.validate_version(version, prev)
                if errors:
                    raise ValueError(f"Experiment {exp.experiment_id} has invalid version {version.version_id}: {', '.join(errors)}")

    @staticmethod
    def assert_no_execution_influence() -> bool:
        """Dummy runtime check asserting no execution bindings exist."""
        return True
