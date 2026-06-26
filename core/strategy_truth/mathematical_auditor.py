from dataclasses import dataclass
from enum import Enum
from core.strategy_truth.control_flow import StrategyDecisionGraph


class MathematicalClassification(Enum):
    MATHEMATICAL_MATCH = "MATHEMATICAL_MATCH"
    MATHEMATICAL_PARTIAL_MATCH = "MATHEMATICAL_PARTIAL_MATCH"
    MATHEMATICAL_STRUCTURE_WEAK = "MATHEMATICAL_STRUCTURE_WEAK"
    MATHEMATICAL_MISMATCH = "MATHEMATICAL_MISMATCH"
    MATHEMATICAL_UNABLE_TO_VERIFY = "MATHEMATICAL_UNABLE_TO_VERIFY"


@dataclass
class MathematicalResult:
    classification: MathematicalClassification
    reason: str


class MathematicalAuditor:
    """Verifies whether implementation logic matches the mathematical structure of the claimed strategy."""
    
    def __init__(self, cfg: StrategyDecisionGraph, strategy_description: str):
        self.cfg = cfg
        self.strategy_description = strategy_description.lower()

    def audit(self) -> MathematicalResult:
        if not self.cfg.is_reconstructable:
            return MathematicalResult(
                classification=MathematicalClassification.MATHEMATICAL_UNABLE_TO_VERIFY,
                reason="Control flow graph is too complex to reconstruct mathematically."
            )

        all_text = " ".join([n.normalized_expression for n in self.cfg.nodes])
        
        # Check VWAP Pullback Structure
        if "vwap pullback" in self.strategy_description:
            has_reference = "vwap" in all_text
            has_pullback = "pullback" in all_text or "<" in all_text or ">" in all_text # naive math structure
            has_confirm = "confirm" in all_text or "cross" in all_text
            
            if has_reference and has_pullback and has_confirm:
                return MathematicalResult(MathematicalClassification.MATHEMATICAL_MATCH, "Proper VWAP pullback mathematical structure detected.")
            elif has_reference and has_pullback:
                return MathematicalResult(MathematicalClassification.MATHEMATICAL_PARTIAL_MATCH, "Missing strict confirmation structure.")
            else:
                return MathematicalResult(MathematicalClassification.MATHEMATICAL_STRUCTURE_WEAK, "Implementation relies on loose indicator checks, lacks full VWAP structural math.")

        # Check Mean Reversion Structure
        if "mean reversion" in self.strategy_description:
            has_extension = "extension" in all_text or "distance" in all_text or "-" in all_text
            has_exhaustion = "exhaust" in all_text or "divergence" in all_text or "rsi" in all_text
            
            if has_extension and has_exhaustion:
                return MathematicalResult(MathematicalClassification.MATHEMATICAL_MATCH, "Proper mean reversion structural math detected.")
            elif has_extension:
                return MathematicalResult(MathematicalClassification.MATHEMATICAL_STRUCTURE_WEAK, "Mean reversion lacks exhaustion mathematical check.")
            else:
                return MathematicalResult(MathematicalClassification.MATHEMATICAL_MISMATCH, "Does not match mean reversion mathematics.")

        # Check ORB Structure
        if "orb" in self.strategy_description or "opening range" in self.strategy_description:
            has_window = "time" in all_text or "session" in all_text or "9:" in all_text
            has_breakout = ">" in all_text or "<" in all_text or "break" in all_text
            
            if has_window and has_breakout:
                return MathematicalResult(MathematicalClassification.MATHEMATICAL_MATCH, "Proper ORB structural math detected.")
            else:
                return MathematicalResult(MathematicalClassification.MATHEMATICAL_MISMATCH, "ORB without opening range window math is a mismatch.")

        return MathematicalResult(
            classification=MathematicalClassification.MATHEMATICAL_UNABLE_TO_VERIFY,
            reason="No known mathematical paradigm claimed."
        )
