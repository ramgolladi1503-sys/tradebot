from dataclasses import dataclass
from typing import Set

@dataclass(frozen=True)
class GraphNode:
    id: str
    type: str # 'regulatory_body', 'sector', 'index', 'instrument', 'metric'

@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    relationship: str # 'impacts', 'regulates', 'comprises'
    is_inferred: bool
    evidence_pointer: str

class KnowledgeGraph:
    def __init__(self):
        self.nodes: Set[GraphNode] = set()
        self.edges: Set[GraphEdge] = set()

    def add_node(self, node: GraphNode) -> None:
        self.nodes.add(node)

    def add_edge(self, edge: GraphEdge) -> None:
        # Prevent hallucinated edges by requiring explicit evidence for anything inferred
        if edge.is_inferred and not edge.evidence_pointer:
            raise ValueError("Inferred edges must have explicit evidence pointers.")
        self.edges.add(edge)

# Pre-configured, non-hallucinated canonical nodes
NODE_RBI = GraphNode("RBI", "regulatory_body")
NODE_BANKING = GraphNode("Banking", "sector")
NODE_BANKNIFTY = GraphNode("BANKNIFTY", "index")

# Explicit, typed static config relationships (no LLM hallucination required)
CANONICAL_EDGES = [
    GraphEdge("RBI", "Banking", "regulates", is_inferred=False, evidence_pointer="StaticConfig"),
    GraphEdge("Banking", "BANKNIFTY", "comprises", is_inferred=False, evidence_pointer="StaticConfig")
]
