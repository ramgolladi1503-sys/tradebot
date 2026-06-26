import ast
from typing import List
from core.strategy_truth.truth_models import RuleEvidence


class RuleExtractor:
    """Extracts rule evidence from AST parsing."""

    def __init__(self, strategy_id: str, file_path: str):
        self.strategy_id = strategy_id
        self.file_path = file_path
        with open(file_path, "r", encoding="utf-8") as f:
            self.source_code = f.read()

    def _get_evidence_type(self, text: str, node_name: str) -> str:
        text_lower = text.lower()
        name_lower = node_name.lower()
        combined = text_lower + " " + name_lower

        if "time" in combined and "stop" in combined:
            return "time-stop"
        elif "stop" in combined:
            return "stop logic"
        elif "target" in combined or "take_profit" in combined:
            return "target logic"
        elif "entry" in combined or "enter" in combined or "buy" in combined:
            return "entry conditions"
        elif "exit" in combined or "close" in combined or "sell" in combined:
            return "exit conditions"
        elif "confirm" in combined:
            return "confirmations"
        elif "filter" in combined:
            return "filters"
        elif "regime" in combined:
            return "regime gates"
        elif "liquid" in combined or "spread" in combined:
            return "liquidity gates"
        elif "fresh" in combined or "age" in combined:
            return "quote freshness gates"
        elif "option" in combined and ("select" in combined or "strike" in combined):
            return "option-selection logic"
        return "unknown"

    def extract(self) -> List[RuleEvidence]:
        tree = ast.parse(self.source_code, filename=self.file_path)
        evidence_list = []

        # Find docstrings of classes/functions, and simple assignment values that look like rules
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                docstring = ast.get_docstring(node)
                if docstring:
                    for i, line in enumerate(docstring.splitlines()):
                        if not line.strip():
                            continue
                        evidence_type = self._get_evidence_type(line, node.name)
                        if evidence_type != "unknown":
                            evidence_list.append(
                                RuleEvidence(
                                    strategy_id=self.strategy_id,
                                    file_path=self.file_path,
                                    function_or_class_name=node.name,
                                    evidence_text=line.strip(),
                                    evidence_type=evidence_type,
                                    extraction_confidence="high",
                                    line_number=node.lineno,  # Approx line number
                                )
                            )
                # Also check method bodies for rule logic (e.g. if statements)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for child in ast.walk(node):
                        if isinstance(child, ast.If):
                            # Try to extract the condition source code
                            # In a real AST unparser this would be better, but we can just use the line if single line
                            condition_line = child.lineno
                            evidence_type = self._get_evidence_type("", node.name)
                            if evidence_type != "unknown":
                                evidence_list.append(
                                    RuleEvidence(
                                        strategy_id=self.strategy_id,
                                        file_path=self.file_path,
                                        function_or_class_name=node.name,
                                        evidence_text=f"If condition at line {condition_line}",
                                        evidence_type=evidence_type,
                                        extraction_confidence="medium",
                                        line_number=condition_line,
                                    )
                                )

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        evidence_type = self._get_evidence_type("", target.id)
                        if evidence_type != "unknown":
                            val_str = ""
                            if isinstance(node.value, ast.Constant):
                                val_str = str(node.value.value)
                            elif isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                                val_str = "collection"
                            
                            evidence_list.append(
                                RuleEvidence(
                                    strategy_id=self.strategy_id,
                                    file_path=self.file_path,
                                    function_or_class_name="global",
                                    evidence_text=f"{target.id} = {val_str}",
                                    evidence_type=evidence_type,
                                    extraction_confidence="medium",
                                    line_number=node.lineno,
                                )
                            )

        return evidence_list
