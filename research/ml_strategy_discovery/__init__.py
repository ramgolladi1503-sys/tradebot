"""Offline, research-only machine-learning strategy discovery primitives.

This package deliberately has no runtime, broker, order, strategy, dashboard, or
live-execution imports. It produces research candidates only; independent
backtesting and human approval are required before any downstream use.
"""

from .audit import AuditReport, audit_candidate, audit_observations
from .contracts import (
    BarrierSpec,
    CandidateStatus,
    CandidateStrategySpec,
    DiscoveryObservation,
    FeatureValue,
    SafetyEnvelope,
    semantic_hash,
)
from .dataset import LabeledObservation, build_feature_matrix
from .labels import Bar, BarrierOutcome, Side, TripleBarrierLabel, label_triple_barrier
from .models import DiscoveryModelConfig, fit_shallow_tree, fit_xgboost_classifier
from .negative_controls import (
    delayed_series,
    deterministic_permutation,
    parameter_neighborhood,
    randomized_entry_offsets,
)
from .registry import CandidateRegistry
from .rules import ExtractedRule, RuleCondition, extract_positive_leaf_rules
from .splits import (
    DatasetPartitionPlan,
    WalkForwardFold,
    make_anchored_walk_forward,
    make_chronological_partitions,
)

__all__ = [
    "AuditReport",
    "Bar",
    "BarrierOutcome",
    "BarrierSpec",
    "CandidateRegistry",
    "CandidateStatus",
    "CandidateStrategySpec",
    "DatasetPartitionPlan",
    "DiscoveryModelConfig",
    "DiscoveryObservation",
    "ExtractedRule",
    "FeatureValue",
    "LabeledObservation",
    "RuleCondition",
    "SafetyEnvelope",
    "Side",
    "TripleBarrierLabel",
    "WalkForwardFold",
    "audit_candidate",
    "audit_observations",
    "build_feature_matrix",
    "delayed_series",
    "deterministic_permutation",
    "extract_positive_leaf_rules",
    "fit_shallow_tree",
    "fit_xgboost_classifier",
    "label_triple_barrier",
    "make_anchored_walk_forward",
    "make_chronological_partitions",
    "parameter_neighborhood",
    "randomized_entry_offsets",
    "semantic_hash",
]
