import json
import logging
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from core.research_registry.hypothesis_registry import HypothesisRegistry
from core.research_registry.experiment_registry import ExperimentRegistry
from core.research_registry.research_models import (
    ResearchHypothesis, ResearchExperiment, ExperimentVersion,
    ParameterSet, MarketUniverse, ExperimentResultReference, ResearchEvidence
)
from core.research_registry.research_types import ResearchStage
from core.paths import repo_root

logger = logging.getLogger(__name__)


class ResearchLoaderError(Exception):
    """Validation or load error for research registry data."""
    pass


class DiskResearchLoader:
    """
    Loads research artifacts from disk.
    Reads from `<base_dir>/hypotheses/*.json` and `<base_dir>/experiments/*.json`.
    Validates structure and ensures strict checking.
    """

    def __init__(self, hypothesis_registry: HypothesisRegistry, experiment_registry: ExperimentRegistry, base_dir: str | Path | None = None):
        self.hypothesis_registry = hypothesis_registry
        self.experiment_registry = experiment_registry
        
        if base_dir is None:
            self.base_dir = repo_root() / "research"
        else:
            self.base_dir = Path(base_dir)

    def load_all(self) -> None:
        """
        Loads all hypotheses and experiments from disk into the registries.
        Raises ResearchLoaderError if validation fails.
        """
        hypotheses_dir = self.base_dir / "hypotheses"
        experiments_dir = self.base_dir / "experiments"

        if not self.base_dir.exists() or (not hypotheses_dir.exists() and not experiments_dir.exists()):
            # Nothing to load. The orchestrator / registry runner will handle the empty case.
            return

        # 1. Load Hypotheses
        if hypotheses_dir.exists():
            for filepath in hypotheses_dir.glob("*.json"):
                self._load_hypothesis_file(filepath)

        # 2. Load Experiments
        if experiments_dir.exists():
            for filepath in experiments_dir.glob("*.json"):
                self._load_experiment_file(filepath)

    def _load_hypothesis_file(self, filepath: Path) -> None:
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ResearchLoaderError(f"Malformed JSON in {filepath}: {e}")

        required_fields = ["hypothesis_id", "title", "description", "created_timestamp", "author"]
        for field in required_fields:
            if field not in data:
                raise ResearchLoaderError(f"Missing '{field}' in {filepath}")

        try:
            created_timestamp = datetime.fromisoformat(data["created_timestamp"].replace('Z', '+00:00'))
        except ValueError:
            raise ResearchLoaderError(f"Invalid created_timestamp format in {filepath}")

        hyp = ResearchHypothesis(
            hypothesis_id=data["hypothesis_id"],
            title=data["title"],
            description=data["description"],
            created_timestamp=created_timestamp,
            author=data["author"]
        )

        if self.hypothesis_registry.get(hyp.hypothesis_id) is not None:
            raise ResearchLoaderError(f"Duplicate hypothesis_id: {hyp.hypothesis_id}")

        self.hypothesis_registry.register(hyp)

    def _load_experiment_file(self, filepath: Path) -> None:
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ResearchLoaderError(f"Malformed JSON in {filepath}: {e}")

        required_fields = ["experiment_id", "parent_hypothesis_id", "versions"]
        for field in required_fields:
            if field not in data:
                raise ResearchLoaderError(f"Missing '{field}' in {filepath}")

        experiment_id = data["experiment_id"]
        parent_hypothesis_id = data["parent_hypothesis_id"]

        if self.experiment_registry.get(experiment_id) is not None:
            raise ResearchLoaderError(f"Duplicate experiment_id: {experiment_id}")

        evidence = ResearchEvidence()
        if "evidence" in data:
            ev_data = data["evidence"]
            evidence = ResearchEvidence(
                strategy_registry_id=ev_data.get("strategy_registry_id"),
                truth_engine_report_id=ev_data.get("truth_engine_report_id"),
                outcome_evidence_id=ev_data.get("outcome_evidence_id"),
                statistical_validation_id=ev_data.get("statistical_validation_id"),
                certification_id=ev_data.get("certification_id")
            )

        exp = ResearchExperiment(
            experiment_id=experiment_id,
            parent_hypothesis_id=parent_hypothesis_id,
            versions=[],
            evidence=evidence
        )

        self.experiment_registry.register(exp)

        # Parse versions
        for v_data in data["versions"]:
            version = self._parse_version(v_data, filepath)
            
            # Check for duplicate version IDs within this experiment
            if any(v.version_id == version.version_id for v in exp.versions):
                raise ResearchLoaderError(f"Duplicate version_id '{version.version_id}' in {filepath}")
                
            exp.versions.append(version)

    def _parse_version(self, v_data: Dict[str, Any], filepath: Path) -> ExperimentVersion:
        required_fields = [
            "version_id", "created_timestamp", "author", "branch", "commit",
            "market_universe", "parameters", "reason", "result", "stage"
        ]
        for field in required_fields:
            if field not in v_data:
                raise ResearchLoaderError(f"Missing '{field}' in version inside {filepath}")

        try:
            created_timestamp = datetime.fromisoformat(v_data["created_timestamp"].replace('Z', '+00:00'))
        except ValueError:
            raise ResearchLoaderError(f"Invalid created_timestamp format in version inside {filepath}")

        # Market Universe
        mu_data = v_data["market_universe"]
        for field in ["dataset", "market", "timeframe"]:
            if field not in mu_data:
                raise ResearchLoaderError(f"Missing market_universe '{field}' inside {filepath}")
        mu = MarketUniverse(
            dataset=mu_data["dataset"],
            market=mu_data["market"],
            timeframe=mu_data["timeframe"]
        )

        # Parameters
        param_data = v_data["parameters"]
        if "parameters" not in param_data:
            raise ResearchLoaderError(f"Missing parameters dict in {filepath}")
        params = ParameterSet(parameters=param_data["parameters"])

        # Result
        res_data = v_data["result"]
        for field in ["expected_behavior", "actual_behavior", "limitations", "conclusion"]:
            if field not in res_data:
                raise ResearchLoaderError(f"Missing result '{field}' inside {filepath}")
        res = ExperimentResultReference(
            expected_behavior=res_data["expected_behavior"],
            actual_behavior=res_data["actual_behavior"],
            limitations=res_data["limitations"],
            conclusion=res_data["conclusion"]
        )

        try:
            stage = ResearchStage[v_data["stage"]]
        except KeyError:
            raise ResearchLoaderError(f"Invalid stage '{v_data['stage']}' inside {filepath}")

        return ExperimentVersion(
            version_id=v_data["version_id"],
            created_timestamp=created_timestamp,
            author=v_data["author"],
            branch=v_data["branch"],
            commit=v_data["commit"],
            market_universe=mu,
            parameters=params,
            reason=v_data["reason"],
            result=res,
            stage=stage
        )
