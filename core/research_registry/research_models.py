from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from core.research_registry.research_types import ResearchStage, PromotionStatus


@dataclass(frozen=True)
class ParameterSet:
    """Immutable representation of parameters used in an experiment."""
    parameters: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketUniverse:
    """Immutable definition of the market context for an experiment."""
    dataset: str
    market: str
    timeframe: str


@dataclass(frozen=True)
class ExperimentResultReference:
    """A reference to the generated result/report for an experiment."""
    expected_behavior: str
    actual_behavior: str
    limitations: List[str]
    conclusion: str


@dataclass(frozen=True)
class ResearchEvidence:
    """Links to downstream evidence systems."""
    strategy_registry_id: Optional[str] = None
    truth_engine_report_id: Optional[str] = None
    outcome_evidence_id: Optional[str] = None
    statistical_validation_id: Optional[str] = None
    certification_id: Optional[str] = None


@dataclass(frozen=True)
class ExperimentVersion:
    """A specific immutable version of a research experiment."""
    version_id: str
    created_timestamp: datetime
    author: str
    branch: str
    commit: str
    market_universe: MarketUniverse
    parameters: ParameterSet
    reason: str
    result: ExperimentResultReference
    stage: ResearchStage


@dataclass(frozen=True)
class ResearchExperiment:
    """A collection of experiment versions that belong to a parent hypothesis."""
    experiment_id: str
    parent_hypothesis_id: str
    versions: List[ExperimentVersion] = field(default_factory=list)
    evidence: ResearchEvidence = field(default_factory=ResearchEvidence)


@dataclass(frozen=True)
class ResearchHypothesis:
    """The root of the idea lineage."""
    hypothesis_id: str
    title: str
    description: str
    created_timestamp: datetime
    author: str


@dataclass(frozen=True)
class PromotionRecommendation:
    """The output of the Promotion Policy."""
    status: PromotionStatus
    reasons: List[str]
    target_stage: Optional[ResearchStage]


@dataclass(frozen=True)
class ResearchDecision:
    """A formal decision record attached to an experiment."""
    experiment_id: str
    version_id: str
    decision_timestamp: datetime
    author: str
    recommendation: PromotionRecommendation


@dataclass(frozen=True)
class ResearchRegistryReport:
    """The complete aggregated output state of the registry."""
    timestamp: datetime
    hypotheses: List[ResearchHypothesis]
    experiments: List[ResearchExperiment]
    decisions: List[ResearchDecision]
