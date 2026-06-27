from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
from core.strategy_truth.semantic_vocabulary import get_semantic_vocabulary, SemanticConcept
from core.strategy_truth.decision_graph import DecisionGraphBuilder
from core.strategy_truth.control_flow import StrategyDecisionGraph, NodeType


class SemanticClassification(Enum):
    SEMANTIC_MATCH = "SEMANTIC_MATCH"
    SEMANTIC_PARTIAL_MATCH = "SEMANTIC_PARTIAL_MATCH"
    SEMANTIC_MISMATCH = "SEMANTIC_MISMATCH"
    SEMANTIC_CONTRADICTION = "SEMANTIC_CONTRADICTION"
    SEMANTIC_UNABLE_TO_VERIFY = "SEMANTIC_UNABLE_TO_VERIFY"
    SEMANTIC_REGISTRY_INCOMPLETE = "SEMANTIC_REGISTRY_INCOMPLETE"


@dataclass
class SemanticResult:
    classification: SemanticClassification
    expected_concept: str
    graph_evidence: str
    missing_evidence: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    reason: str = ""


class SemanticComparator:
    """Compares registry contract + semantic vocabulary + decision graph."""

    def __init__(self, cfg: StrategyDecisionGraph, strategy_description: str):
        self.cfg = cfg
        self.strategy_description = strategy_description.lower()
        self.builder = DecisionGraphBuilder(cfg)
        self.vocabulary = get_semantic_vocabulary()

    def _determine_expected_concept(self) -> Optional[SemanticConcept]:
        for concept_key, concept in self.vocabulary.items():
            if concept_key in self.strategy_description:
                return concept
        return None

    def _check_ordering_flaws(self) -> List[SemanticResult]:
        flaws: list[SemanticResult] = []
        if not self.cfg.is_reconstructable:
            return flaws

        # Find candidate creation nodes
        candidate_indices = [
            i for i, node in enumerate(self.cfg.nodes)
            if node.node_type == NodeType.CANDIDATE_CREATION
        ]
        
        blocker_indices = [
            i for i, node in enumerate(self.cfg.nodes)
            if node.node_type == NodeType.BLOCKER
        ]

        if candidate_indices and blocker_indices:
            first_candidate = candidate_indices[0]
            for blocker_idx in blocker_indices:
                if blocker_idx > first_candidate:
                    node = self.cfg.nodes[blocker_idx]
                    flaws.append(
                        SemanticResult(
                            classification=SemanticClassification.SEMANTIC_CONTRADICTION,
                            expected_concept="blockers before candidate creation",
                            graph_evidence=f"Blocker at line {node.line_number}",
                            missing_evidence="",
                            file_path=node.file_path,
                            line_number=node.line_number,
                            reason="Blocker applied after candidate creation."
                        )
                    )

        return flaws

    def compare(self) -> List[SemanticResult]:
        if not self.cfg.is_reconstructable:
            return [
                SemanticResult(
                    classification=SemanticClassification.SEMANTIC_UNABLE_TO_VERIFY,
                    expected_concept="Control flow graph",
                    graph_evidence="",
                    missing_evidence="Graph could not be reconstructed",
                    reason="Complex or ambiguous logic prevented control flow reconstruction."
                )
            ]

        results = []
        ordering_flaws = self._check_ordering_flaws()
        results.extend(ordering_flaws)

        expected_concept = self._determine_expected_concept()
        if not expected_concept:
            # Cannot semantically verify if we don't know the paradigm
            results.append(
                SemanticResult(
                    classification=SemanticClassification.SEMANTIC_PARTIAL_MATCH,
                    expected_concept="Known trading concept",
                    graph_evidence="",
                    missing_evidence="",
                    reason="No recognized semantic paradigm found in description. Cannot perform deep semantic check."
                )
            )
            return results

        all_text = " ".join([n.normalized_expression for n in self.cfg.nodes])

        missing_required = []
        for req in expected_concept.required_patterns:
            # We look for the required pattern concepts in the logic (very loose approximation for the purpose of the truth engine without executing)
            # In a real compiler, we would structurally match. Here we check if the concept is represented in the decision graph.
            if not any(req_word in all_text for req_word in req.split("/")):
                missing_required.append(req)

        contradictions = []
        for contra in expected_concept.contradiction_patterns:
            if any(contra_word in all_text for contra_word in contra.split("/")):
                contradictions.append(contra)

        if contradictions:
            results.append(
                SemanticResult(
                    classification=SemanticClassification.SEMANTIC_CONTRADICTION,
                    expected_concept=expected_concept.name,
                    graph_evidence=f"Found contradictions: {contradictions}",
                    missing_evidence="",
                    reason="Contradictory conditions found in decision graph."
                )
            )
        elif missing_required:
            results.append(
                SemanticResult(
                    classification=SemanticClassification.SEMANTIC_MISMATCH,
                    expected_concept=expected_concept.name,
                    graph_evidence="",
                    missing_evidence=f"Missing: {missing_required}",
                    reason="Required concepts present only as keywords but not in decision logic."
                )
            )
        else:
            results.append(
                SemanticResult(
                    classification=SemanticClassification.SEMANTIC_MATCH,
                    expected_concept=expected_concept.name,
                    graph_evidence="All required concepts present in logic.",
                    missing_evidence="",
                    reason="Semantic logic matches declared concept."
                )
            )

        return results
