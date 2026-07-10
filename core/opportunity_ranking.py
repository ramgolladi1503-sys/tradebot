from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class CandidateOpportunity:
    symbol: str
    strategy_id: str
    edge_evidence_score: float
    regime_compatibility_score: float
    liquidity_spread_score: float
    quote_freshness_ms: int
    cost_hurdle_passed: bool
    truth_quality_score: float
    is_fallback_or_recovered_quote: bool
    
    # Required for UI output shape
    advisory_only: bool = field(init=False)
    final_rank_score: float = field(init=False)

    def __post_init__(self):
        # Critical Safety Guard: Fallback or recovered quotes must never be executable.
        if self.is_fallback_or_recovered_quote:
            self.advisory_only = True
        else:
            self.advisory_only = False

        # Compute rank score based on provided inputs
        # This is a read-only mathematical representation of execution readiness
        if not self.cost_hurdle_passed:
            self.final_rank_score = 0.0
        else:
            self.final_rank_score = (
                self.edge_evidence_score * 0.4 +
                self.regime_compatibility_score * 0.2 +
                self.truth_quality_score * 0.3 +
                self.liquidity_spread_score * 0.1
            )
            # Penalty for stale quotes
            if self.quote_freshness_ms > 1000:
                self.final_rank_score *= 0.5


def rank_opportunities(candidates: List[CandidateOpportunity]) -> dict:
    """
    Ranks the given candidate opportunities strictly as a read-only output.
    This never executes orders.
    """
    ranked = sorted(candidates, key=lambda c: c.final_rank_score, reverse=True)
    
    return {
        "TOP_OPPORTUNITIES": [
            {
                "symbol": c.symbol,
                "strategy_id": c.strategy_id,
                "score": round(c.final_rank_score, 2),
                "advisory_only": c.advisory_only
            } for c in ranked if c.final_rank_score > 0
        ],
        "ALL_CANDIDATES_DEBUG": [
            {
                "symbol": c.symbol,
                "strategy_id": c.strategy_id,
                "edge_score": c.edge_evidence_score,
                "regime_score": c.regime_compatibility_score,
                "cost_passed": c.cost_hurdle_passed,
                "is_fallback": c.is_fallback_or_recovered_quote,
                "advisory_only": c.advisory_only,
                "final_rank_score": round(c.final_rank_score, 2)
            } for c in ranked
        ]
    }
