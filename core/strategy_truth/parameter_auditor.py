import ast
from typing import List
from core.strategy_truth.truth_types import ParameterClassification
from core.strategy_truth.truth_models import ParameterFinding


class ParameterAuditor:
    """Finds parameters, thresholds, literals, and constants in strategy files."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        with open(file_path, "r", encoding="utf-8") as f:
            self.source_code = f.read()

    def _classify_parameter(self, name: str, is_constant: bool) -> ParameterClassification:
        name_lower = name.lower()
        if "config" in name_lower or "param" in name_lower:
            return ParameterClassification.DECLARED_CONFIG
        if "rule" in name_lower:
            return ParameterClassification.PUBLISHED_RULE
        if "measure" in name_lower or "stat" in name_lower:
            return ParameterClassification.MEASURED_VALUE
        if "heuristic" in name_lower or "magic" in name_lower:
            return ParameterClassification.HEURISTIC
        if is_constant:
            return ParameterClassification.MAGIC_NUMBER
        return ParameterClassification.UNKNOWN

    def audit(self) -> List[ParameterFinding]:
        tree = ast.parse(self.source_code, filename=self.file_path)
        findings = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, (ast.Name, ast.Attribute)):
                        name = target.id if isinstance(target, ast.Name) else target.attr
                        if isinstance(node.value, ast.Constant):
                            val = str(node.value.value)
                            is_constant = name.isupper()
                            classification = self._classify_parameter(name, is_constant)
                            findings.append(
                                ParameterFinding(
                                    name=name,
                                    value=val,
                                    classification=classification,
                                    file_path=self.file_path,
                                    line_number=node.lineno,
                                )
                            )
                        # Also check if it's a numeric literal assigned
                        elif isinstance(node.value, (ast.UnaryOp, ast.BinOp)):
                            is_constant = name.isupper()
                            classification = self._classify_parameter(name, is_constant)
                            findings.append(
                                ParameterFinding(
                                    name=name,
                                    value="expression",
                                    classification=classification,
                                    file_path=self.file_path,
                                    line_number=node.lineno,
                                )
                            )

        return findings
