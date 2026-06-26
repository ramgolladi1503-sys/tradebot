import ast
import tokenize
import io
from core.strategy_truth.truth_models import StrategySourceEvidence


class SourceScanner:
    """Safe read-only AST parser for strategy files."""

    def __init__(self, strategy_id: str, file_path: str):
        self.strategy_id = strategy_id
        self.file_path = file_path
        with open(file_path, "r", encoding="utf-8") as f:
            self.source_code = f.read()

    def scan(self) -> StrategySourceEvidence:
        tree = ast.parse(self.source_code, filename=self.file_path)

        classes = []
        functions = []
        constants = []
        imported_modules = []
        indicator_names = set()
        candidate_creation_calls = []
        ranking_hooks = []
        execution_hooks = []
        blocker_gate_references = set()
        parameter_literals = set()

        # Simple keywords for identifying hooks/gates/indicators
        indicator_keywords = {"RSI", "ATR", "VWAP", "EMA", "SMA", "ADX", "entropy", "volume", "OI", "IV", "Greeks", "momentum", "market_structure", "ORB", "liquidity", "spread"}
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                functions.append(node.name)
                # Check for ranking/execution hooks by name
                if "rank" in node.name.lower():
                    ranking_hooks.append(node.name)
                if "exec" in node.name.lower() or "order" in node.name.lower():
                    execution_hooks.append(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id.isupper():
                            constants.append(target.id)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_modules.append(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                    if "candidate" in func_name.lower() or "create" in func_name.lower():
                        candidate_creation_calls.append(func_name)
                    if "gate" in func_name.lower() or "block" in func_name.lower():
                        blocker_gate_references.add(func_name)
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                    if "candidate" in func_name.lower():
                        candidate_creation_calls.append(func_name)
                    if "gate" in func_name.lower() or "block" in func_name.lower():
                        blocker_gate_references.add(func_name)
            elif isinstance(node, ast.Name):
                name_upper = node.id.upper()
                for kw in indicator_keywords:
                    if kw.upper() in name_upper:
                        indicator_names.add(node.id)
                if "GATE" in name_upper or "BLOCKER" in name_upper:
                    blocker_gate_references.add(node.id)
            elif isinstance(node, ast.Attribute):
                name_upper = node.attr.upper()
                for kw in indicator_keywords:
                    if kw.upper() in name_upper:
                        indicator_names.add(node.attr)
                if "GATE" in name_upper or "BLOCKER" in name_upper:
                    blocker_gate_references.add(node.attr)
            elif isinstance(node, ast.Constant):
                if isinstance(node.value, (int, float)):
                    parameter_literals.add(str(node.value))

        # Extract comments
        comments = []
        tokens = tokenize.tokenize(io.BytesIO(self.source_code.encode("utf-8")).readline)
        for tok in tokens:
            if tok.type == tokenize.COMMENT:
                comment_text = tok.string.strip()
                if "assume" in comment_text.lower() or "assumption" in comment_text.lower():
                    comments.append(comment_text)

        return StrategySourceEvidence(
            strategy_id=self.strategy_id,
            classes=list(classes),
            functions=list(functions),
            constants=list(constants),
            imported_modules=list(set(imported_modules)),
            indicator_names=list(indicator_names),
            candidate_creation_calls=list(set(candidate_creation_calls)),
            ranking_hooks=list(set(ranking_hooks)),
            execution_hooks=list(set(execution_hooks)),
            blocker_gate_references=list(blocker_gate_references),
            parameter_literals=list(parameter_literals),
            comments=comments,
        )
