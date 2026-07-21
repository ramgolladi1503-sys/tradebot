"""Research-only, causal and interpretable ML strategy discovery."""

from .audit import build_evidence_manifest
from .contracts import (
    DiscoveryConfig,
    FeatureImputation,
    StrategyCandidate,
    TimestampSemantics,
)
from .dataset import build_discovery_dataset, chronological_split
from .evaluation import evaluate_candidate, evaluate_locked_holdout_once
from .models import train_discovery_models
from .upstox_source import UpstoxSourceBundle, load_certified_upstox_underlying

__all__ = [
    "DiscoveryConfig",
    "FeatureImputation",
    "StrategyCandidate",
    "TimestampSemantics",
    "UpstoxSourceBundle",
    "build_discovery_dataset",
    "chronological_split",
    "train_discovery_models",
    "evaluate_candidate",
    "evaluate_locked_holdout_once",
    "build_evidence_manifest",
    "load_certified_upstox_underlying",
]
