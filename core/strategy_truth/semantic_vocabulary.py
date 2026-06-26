from dataclasses import dataclass
from typing import List, Dict


@dataclass
class SemanticConcept:
    name: str
    required_patterns: List[str]
    optional_patterns: List[str]
    contradiction_patterns: List[str]
    explanation: str


def get_semantic_vocabulary() -> Dict[str, SemanticConcept]:
    """
    Map common strategy concepts to implementation evidence patterns.
    This is not trading edge. It is implementation intent mapping.
    """
    return {
        "vwap pullback": SemanticConcept(
            name="VWAP Pullback",
            required_patterns=["vwap", "pullback/retest", "reversal/confirm"],
            optional_patterns=["distance", "trend/regime"],
            contradiction_patterns=["mean reversion", "exhaustion"],
            explanation="Requires vwap reference, pullback/retest condition, and a confirmation condition."
        ),
        "mean reversion": SemanticConcept(
            name="Mean Reversion",
            required_patterns=["extension/distance/-", "exhaustion/divergence/rsi", "reversion/target"],
            optional_patterns=["range/regime", "stop/invalidation"],
            contradiction_patterns=["trend following", "breakout"],
            explanation="Requires extension from fair value, exhaustion condition, and reversion target."
        ),
        "orb": SemanticConcept(
            name="ORB",
            required_patterns=["time/session/9:", "breakout/>/<", "confirm"],
            optional_patterns=["false breakout filter", "session timing"],
            contradiction_patterns=["mean reversion"],
            explanation="Requires opening range construction, breakout level, and breakout confirmation."
        ),
        "trend following": SemanticConcept(
            name="Trend Following",
            required_patterns=["trend strength", "directional bias", "pullback/continuation"],
            optional_patterns=["invalidation stop"],
            contradiction_patterns=["mean reversion", "exhaustion condition"],
            explanation="Requires trend strength, directional bias, and pullback/continuation."
        )
    }
