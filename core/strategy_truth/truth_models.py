from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.strategy_truth.semantic_comparator import SemanticResult
    from core.strategy_truth.mathematical_auditor import MathematicalResult
from core.strategy_truth.truth_types import (
    RuleComparisonStatus,
    ParameterClassification,
    HeuristicClassification,
    IndicatorStatus,
    ImplementationVerdict,
)


@dataclass(frozen=True)
class StrategySourceEvidence:
    strategy_id: str
    classes: List[str]
    functions: List[str]
    constants: List[str]
    imported_modules: List[str]
    indicator_names: List[str]
    candidate_creation_calls: List[str]
    ranking_hooks: List[str]
    execution_hooks: List[str]
    blocker_gate_references: List[str]
    parameter_literals: List[str]
    comments: List[str]


@dataclass(frozen=True)
class RuleEvidence:
    strategy_id: str
    file_path: str
    function_or_class_name: str
    evidence_text: str
    evidence_type: str
    extraction_confidence: str
    line_number: Optional[int] = None


@dataclass(frozen=True)
class RuleComparison:
    registry_field: str
    expected_description: str
    status: RuleComparisonStatus
    reason: str
    implementation_evidence: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None


@dataclass(frozen=True)
class ParameterFinding:
    name: str
    value: str
    classification: ParameterClassification
    file_path: str
    line_number: Optional[int] = None


@dataclass(frozen=True)
class HeuristicFinding:
    keyword_found: str
    context: str
    classification: HeuristicClassification
    file_path: str
    line_number: Optional[int] = None


@dataclass(frozen=True)
class IndicatorFinding:
    indicator_name: str
    status: IndicatorStatus
    reason: str


@dataclass(frozen=True)
class DependencyFinding:
    dependency_name: str
    dependency_type: str
    is_missing: bool = False
    is_unused: bool = False
    is_circular: bool = False
    is_direct_coupling: bool = False
    reason: str = ""


@dataclass(frozen=True)
class StrategyTruthReport:
    strategy_id: str
    is_registry_complete: bool
    verdict: ImplementationVerdict
    source_evidence: StrategySourceEvidence
    rule_comparisons: List[RuleComparison]
    parameter_findings: List[ParameterFinding]
    heuristic_findings: List[HeuristicFinding]
    indicator_findings: List[IndicatorFinding]
    dependency_findings: List[DependencyFinding]
    rule_evidence: List[RuleEvidence] = field(default_factory=list)
    # Hardened Engine Additions
    cfg_is_reconstructable: bool = False
    semantic_results: List['SemanticResult'] = field(default_factory=list)
    mathematical_result: Optional['MathematicalResult'] = None


@dataclass(frozen=True)
class StrategyTruthSummary:
    total_strategies: int
    registry_incomplete_count: int
    fully_verified_count: int
    partially_verified_count: int
    mismatch_count: int
    reports: List[StrategyTruthReport]
