from typing import List
from dataclasses import dataclass, field
from core.strategy_truth.control_flow import StrategyDecisionGraph, CFGNode, NodeType


@dataclass
class LogicPath:
    path_name: str
    nodes: List[CFGNode] = field(default_factory=list)
    has_candidate_emission: bool = False
    has_blocker: bool = False

    def is_ambiguous(self) -> bool:
        """Returns True if this path lacks clear logical closure or is too complex."""
        return len(self.nodes) == 0

    def contains_keyword(self, keyword: str) -> bool:
        kw = keyword.lower()
        return any(kw in n.normalized_expression for n in self.nodes)


class DecisionGraphBuilder:
    """
    Builds logical paths (Entry, Exit, Stop, Target, Filter) from a raw Control Flow Graph.
    """

    def __init__(self, cfg: StrategyDecisionGraph):
        self.cfg = cfg

    def _extract_path_by_keywords(self, path_name: str, keywords: List[str]) -> LogicPath:
        path = LogicPath(path_name=path_name)
        if not self.cfg.is_reconstructable:
            return path
            
        for node in self.cfg.nodes:
            expr = node.normalized_expression
            if any(kw in expr for kw in keywords):
                path.nodes.append(node)
                if node.node_type == NodeType.BLOCKER:
                    path.has_blocker = True
                if node.node_type == NodeType.CANDIDATE_CREATION:
                    path.has_candidate_emission = True
                    
        return path

    def build_entry_graph(self) -> LogicPath:
        return self._extract_path_by_keywords("Entry", ["entry", "enter", "buy", "long", "candidate", "create"])

    def build_exit_graph(self) -> LogicPath:
        return self._extract_path_by_keywords("Exit", ["exit", "close", "sell", "short"])

    def build_stop_graph(self) -> LogicPath:
        return self._extract_path_by_keywords("Stop", ["stop", "sl", "loss"])

    def build_target_graph(self) -> LogicPath:
        return self._extract_path_by_keywords("Target", ["target", "tp", "profit", "take"])

    def build_filter_graph(self) -> LogicPath:
        return self._extract_path_by_keywords("Filter", ["filter", "regime", "spread", "liquid", "fresh"])

    def build_candidate_creation_graph(self) -> LogicPath:
        path = LogicPath("CandidateCreation")
        if not self.cfg.is_reconstructable:
            return path

        for node in self.cfg.nodes:
            if node.node_type == NodeType.CANDIDATE_CREATION:
                path.nodes.append(node)
                path.has_candidate_emission = True
            if node.node_type == NodeType.BLOCKER:
                path.has_blocker = True
        return path
