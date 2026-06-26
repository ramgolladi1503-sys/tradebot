import ast
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class NodeType(Enum):
    DECISION = "decision"
    CONDITION = "condition"
    ACTION = "action"
    BLOCKER = "blocker"
    CANDIDATE_CREATION = "candidate_creation"
    RETURN = "return"
    UNKNOWN = "unknown"


@dataclass
class CFGNode:
    file_path: str
    function_name: str
    line_number: int
    expression_text: str
    normalized_expression: str
    node_type: NodeType


@dataclass
class DecisionEdge:
    from_node: CFGNode
    to_node: CFGNode
    condition_label: str  # e.g., "True", "False", "Sequential"


@dataclass
class StrategyDecisionGraph:
    nodes: List[CFGNode] = field(default_factory=list)
    edges: List[DecisionEdge] = field(default_factory=list)
    is_reconstructable: bool = True


class ControlFlowReconstructor(ast.NodeVisitor):
    """
    Reconstructs control flow paths from AST.
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.graph = StrategyDecisionGraph()
        self.current_function: Optional[str] = None
        self.last_node: Optional[CFGNode] = None

    def _normalize_expr(self, text: str) -> str:
        return text.strip().replace("\n", " ").lower()

    def _create_node(self, node: ast.AST, node_type: NodeType, expr_text: str) -> CFGNode:
        return CFGNode(
            file_path=self.file_path,
            function_name=self.current_function or "global",
            line_number=getattr(node, 'lineno', 0),
            expression_text=expr_text,
            normalized_expression=self._normalize_expr(expr_text),
            node_type=node_type
        )

    def _add_edge(self, from_node: CFGNode, to_node: CFGNode, label: str = "Sequential"):
        self.graph.edges.append(DecisionEdge(from_node=from_node, to_node=to_node, condition_label=label))

    def visit_FunctionDef(self, node: ast.FunctionDef):
        prev_func = self.current_function
        self.current_function = node.name
        self.last_node = None # reset per function
        self.generic_visit(node)
        self.current_function = prev_func

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.visit_FunctionDef(node) # type: ignore

    def visit_If(self, node: ast.If):
        try:
            expr_text = ast.unparse(node.test)
        except Exception:
            expr_text = "complex_condition"
            self.graph.is_reconstructable = False

        decision_node = self._create_node(node.test, NodeType.DECISION, expr_text)
        self.graph.nodes.append(decision_node)
        
        if self.last_node:
            self._add_edge(self.last_node, decision_node)

        # True branch
        self.last_node = decision_node
        for stmt in node.body:
            self.visit(stmt)
            # Edge from decision to first statement in true block is conceptual,
            # but if self.last_node changed, we continue linking sequentially.
        
        last_in_true = self.last_node
        
        # False branch
        self.last_node = decision_node
        for stmt in node.orelse:
            self.visit(stmt)
            
        # Re-merge? This is naive CFG. Real CFG would have a join node.
        # For our purposes we keep it simple, since we mainly care about paths to candidate creation
        self.last_node = last_in_true # Very naive merge

    def visit_Return(self, node: ast.Return):
        expr_text = ast.unparse(node.value) if node.value else "None"
        ret_node = self._create_node(node, NodeType.RETURN, f"return {expr_text}")
        
        # If it looks like an early return blocker (e.g. `return` without candidate)
        if "candidate" not in expr_text.lower():
            ret_node.node_type = NodeType.BLOCKER

        self.graph.nodes.append(ret_node)
        if self.last_node:
            self._add_edge(self.last_node, ret_node)
        self.last_node = ret_node

    def visit_Call(self, node: ast.Call):
        expr_text = ""
        try:
            expr_text = ast.unparse(node)
        except Exception:
            expr_text = "complex_call"
        
        node_type = NodeType.ACTION
        if "candidate" in expr_text.lower():
            node_type = NodeType.CANDIDATE_CREATION
            
        action_node = self._create_node(node, node_type, expr_text)
        self.graph.nodes.append(action_node)
        
        if self.last_node:
            self._add_edge(self.last_node, action_node)
            
        self.last_node = action_node
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        try:
            expr_text = ast.unparse(node)
        except Exception:
            expr_text = "complex_assign"

        node_type = NodeType.ACTION
        if "candidate" in expr_text.lower():
            node_type = NodeType.CANDIDATE_CREATION

        action_node = self._create_node(node, node_type, expr_text)
        self.graph.nodes.append(action_node)
        
        if self.last_node:
            self._add_edge(self.last_node, action_node)
            
        self.last_node = action_node
        self.generic_visit(node)


def build_control_flow_graph(file_path: str, source_code: str) -> StrategyDecisionGraph:
    try:
        tree = ast.parse(source_code, filename=file_path)
        reconstructor = ControlFlowReconstructor(file_path)
        reconstructor.visit(tree)
        return reconstructor.graph
    except Exception:
        return StrategyDecisionGraph(is_reconstructable=False)
