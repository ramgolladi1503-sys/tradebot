"""Research-only, causal and interpretable ML strategy discovery."""

from .audit import build_evidence_manifest
from .contracts import DiscoveryConfig, StrategyCandidate
from .dataset import build_discovery_dataset, chronological_split
from .evaluation import evaluate_candidate, evaluate_locked_holdout_once
from .models import train_discovery_models

__all__ = [
    "DiscoveryConfig",
    "StrategyCandidate",
    "build_discovery_dataset",
    "chronological_split",
    "train_discovery_models",
    "evaluate_candidate",
    "evaluate_locked_holdout_once",
    "build_evidence_manifest",
]
