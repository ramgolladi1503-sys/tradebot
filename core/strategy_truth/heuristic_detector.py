from typing import List
from core.strategy_truth.truth_types import HeuristicClassification
from core.strategy_truth.truth_models import HeuristicFinding


class HeuristicDetector:
    """Detects heuristic and subjective language in strategy implementations."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        with open(file_path, "r", encoding="utf-8") as f:
            self.source_code = f.read()

    def _classify(self, text: str, is_comment: bool) -> HeuristicClassification:
        text_lower = text.lower()
        if is_comment:
            if "todo" in text_lower or "fixme" in text_lower:
                return HeuristicClassification.SAFE_COMMENT
            return HeuristicClassification.SAFE_COMMENT

        if "probability" in text_lower or "chance" in text_lower or "confidence" in text_lower:
            return HeuristicClassification.PROBABILITY_LABEL_RISK
        if "heuristic" in text_lower or "magic" in text_lower or "hardcoded" in text_lower:
            return HeuristicClassification.HEURISTIC_RISK
        if "edge" in text_lower or "score +=" in text_lower:
            return HeuristicClassification.HEURISTIC_RISK
        if "fallback" in text_lower or "advisory" in text_lower:
            return HeuristicClassification.EXECUTION_RISK
        if "threshold" in text_lower:
            return HeuristicClassification.CONFIGURATION

        return HeuristicClassification.UNKNOWN

    def audit(self) -> List[HeuristicFinding]:
        findings = []
        keywords = [
            "todo", "fixme", "heuristic", "magic", "hardcoded", 
            "confidence", "chance", "probability", "edge", 
            "score +=", "threshold", "fallback", "advisory"
        ]

        lines = self.source_code.splitlines()
        for i, line in enumerate(lines):
            line_lower = line.lower()
            for kw in keywords:
                if kw in line_lower:
                    is_comment = "#" in line and line.find("#") <= line_lower.find(kw)
                    classification = self._classify(kw, is_comment)
                    findings.append(
                        HeuristicFinding(
                            keyword_found=kw,
                            context=line.strip(),
                            classification=classification,
                            file_path=self.file_path,
                            line_number=i + 1,
                        )
                    )

        return findings
